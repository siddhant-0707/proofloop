"""Ask Gemma for an answer that validates against a pydantic schema.

Providers are tried in order. A provider that is rate limited or fails is
skipped for the next one.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError


class ProviderError(Exception):
    """A provider could not answer (network, server or quota error)."""


class RateLimited(ProviderError):
    """A provider refused the request because of its rate limit."""


class GenerationFailed(Exception):
    """No provider produced a valid answer."""


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, prompt: str, json_schema: dict[str, Any]) -> str: ...


@dataclass(frozen=True)
class Generation[T: BaseModel]:
    value: T
    provider: str
    model: str
    # Why earlier providers were skipped, e.g. "gemini: RateLimited: 429".
    skipped: list[str] = field(default_factory=list)


class InvalidAnswer(Exception):
    """An answer that does not match the schema or the allowed values."""


Allowed = Mapping[str, Sequence[str]]


class GemmaClient:
    def __init__(self, providers: Sequence[Provider]):
        self._providers = list(providers)

    def generate[T: BaseModel](
        self, system: str, prompt: str, schema: type[T], allowed: Allowed | None = None
    ) -> Generation[T]:
        """Ask each provider in turn for an answer matching `schema`.

        `allowed` restricts named fields (anywhere in the schema) to a set of values,
        e.g. {"shelter_id": ["A", "B"]}.
        """
        allowed = allowed or {}
        skipped: list[str] = []
        for provider in self._providers:
            try:
                value = self._ask(provider, system, prompt, schema, allowed)
            except ProviderError as error:
                skipped.append(f"{provider.name}: {type(error).__name__}: {error}")
                continue
            except InvalidAnswer as error:
                skipped.append(f"{provider.name}: invalid answer: {error}")
                continue
            return Generation(
                value=value, provider=provider.name, model=provider.model, skipped=skipped
            )
        raise GenerationFailed("; ".join(skipped))

    def _ask[T: BaseModel](
        self, provider: Provider, system: str, prompt: str, schema: type[T], allowed: Allowed
    ) -> T:
        """One attempt, plus one retry that shows the model why it was rejected."""
        json_schema = strict_schema(schema, allowed)
        try:
            return _parse(provider.complete(system, prompt, json_schema), schema, allowed)
        except InvalidAnswer as error:
            retry = (
                f"{prompt}\n\nYour previous answer was rejected:\n{error}\n"
                "Answer again with JSON that matches the schema exactly."
            )
            return _parse(provider.complete(system, retry, json_schema), schema, allowed)


def _parse[T: BaseModel](text: str, schema: type[T], allowed: Allowed) -> T:
    try:
        value = schema.model_validate_json(text)
    except ValidationError as error:
        raise InvalidAnswer(_summary(error)) from error
    problems = list(_disallowed(value.model_dump(), allowed, path=""))
    if problems:
        raise InvalidAnswer("; ".join(problems))
    return value


def _disallowed(node: Any, allowed: Allowed, path: str):
    if isinstance(node, dict):
        for key, child in node.items():
            here = f"{path}.{key}" if path else key
            if key in allowed and child not in allowed[key]:
                yield f"{here}: {child!r} is not one of {list(allowed[key])}"
            yield from _disallowed(child, allowed, here)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from _disallowed(child, allowed, f"{path}.{i}")


def strict_schema(schema: type[BaseModel], allowed: Allowed | None = None) -> dict[str, Any]:
    """The schema in the plain form providers enforce best.

    Definitions are inlined, `const` becomes a one-value `enum`, every property is
    required, defaults and titles are dropped, and fields named in `allowed` become
    enums. The answer is still validated against the full model afterwards.
    """
    allowed = allowed or {}
    full = schema.model_json_schema()
    definitions = full.pop("$defs", {})

    def simplify(node: Any) -> Any:
        if isinstance(node, list):
            return [simplify(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return simplify(definitions[node["$ref"].rsplit("/", 1)[-1]])
        out = {k: simplify(v) for k, v in node.items() if k not in ("default", "title")}
        if "const" in out:
            out["enum"] = [out.pop("const")]
        if "properties" in out:
            for name, values in allowed.items():
                if name in out["properties"]:
                    out["properties"][name] = {"type": "string", "enum": list(values)}
            out["required"] = list(out["properties"])
        return out

    return simplify(full)


def _summary(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'answer'}: {e['msg']}" for e in error.errors()
    )
