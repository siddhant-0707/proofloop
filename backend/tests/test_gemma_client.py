"""Gemma client seam: generate(system, prompt, schema) over injected providers."""

import json

import pytest

from proofloop.gemma.client import GemmaClient, GenerationFailed, ProviderError, RateLimited
from proofloop.loop.schemas import Attack, Plan, ShelterOffline

VALID_ATTACK = json.dumps({"type": "shelter_offline", "shelter_id": "A"})


class FakeProvider:
    """Returns scripted responses in order; an Exception in the script is raised instead."""

    def __init__(self, name: str, *script: str | Exception):
        self.name = name
        self.model = f"{name}/gemma"
        self._script = list(script)
        self.calls: list[dict] = []

    def complete(self, system: str, prompt: str, json_schema: dict) -> str:
        self.calls.append({"system": system, "prompt": prompt, "json_schema": json_schema})
        response = self._script.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_returns_the_validated_answer_and_which_provider_gave_it():
    primary = FakeProvider("gemini", VALID_ATTACK)
    client = GemmaClient([primary, FakeProvider("openrouter")])

    generation = client.generate("system", "attack the plan", ShelterOffline)

    assert generation.value == ShelterOffline(shelter_id="A")
    assert (generation.provider, generation.model) == ("gemini", "gemini/gemma")


@pytest.mark.parametrize("failure", [RateLimited("429"), ProviderError("503 overloaded")])
def test_falls_back_to_the_next_provider_when_one_cannot_answer(failure):
    client = GemmaClient(
        [FakeProvider("gemini", failure), FakeProvider("openrouter", VALID_ATTACK)]
    )

    generation = client.generate("system", "attack the plan", ShelterOffline)

    assert generation.provider == "openrouter"
    assert generation.value.shelter_id == "A"


def test_retries_once_with_the_validation_error_when_the_answer_breaks_the_schema():
    wrong = json.dumps({"type": "open", "shelter_id": "A"})
    gemini = FakeProvider("gemini", wrong, VALID_ATTACK)
    client = GemmaClient([gemini, FakeProvider("openrouter")])

    generation = client.generate("system", "attack the plan", ShelterOffline)

    assert generation.provider == "gemini"
    retry_prompt = gemini.calls[1]["prompt"]
    assert retry_prompt.startswith("attack the plan")
    assert "shelter_offline" in retry_prompt  # the validation error names the allowed value


def test_moves_to_the_next_provider_after_two_invalid_answers():
    gemini = FakeProvider("gemini", "not json", "still not json")
    client = GemmaClient([gemini, FakeProvider("openrouter", VALID_ATTACK)])

    generation = client.generate("system", "attack the plan", ShelterOffline)

    assert len(gemini.calls) == 2
    assert generation.provider == "openrouter"


def test_reports_every_provider_failure_when_none_answers():
    client = GemmaClient(
        [FakeProvider("gemini", RateLimited("429")), FakeProvider("openrouter", "nope", "nope")]
    )

    with pytest.raises(GenerationFailed) as failed:
        client.generate("system", "attack the plan", ShelterOffline)

    message = str(failed.value)
    assert "gemini: RateLimited: 429" in message
    assert "openrouter: invalid answer" in message


def test_sends_providers_a_strict_schema_they_can_enforce():
    gemini = FakeProvider("gemini", VALID_ATTACK)

    GemmaClient([gemini]).generate("system", "attack the plan", ShelterOffline)

    assert gemini.calls[0]["json_schema"] == {
        "type": "object",
        "properties": {
            "rationale": {"type": "string", "maxLength": 400},
            "type": {"type": "string", "enum": ["shelter_offline"]},
            "shelter_id": {"type": "string"},
        },
        "required": ["rationale", "type", "shelter_id"],
        "additionalProperties": False,
    }


def test_inlines_nested_definitions_for_providers():
    gemini = FakeProvider(
        "gemini",
        json.dumps(
            {
                "actions": [{"type": "open_shelter", "shelter_id": "A"}],
                "claims": {"cost": 100, "people_sheltered": 10},
                "rationale": "r",
            }
        ),
    )

    GemmaClient([gemini]).generate("system", "plan", Plan)

    schema = gemini.calls[0]["json_schema"]
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)
    variants = schema["properties"]["actions"]["items"]["anyOf"]
    assert {"type": "string", "enum": ["open_shelter"]} in [
        v["properties"]["type"] for v in variants
    ]
    assert schema["required"] == ["rationale", "actions", "claims"]  # reason before numbers


def test_restricts_named_fields_to_the_allowed_values():
    gemini = FakeProvider("gemini", VALID_ATTACK)

    GemmaClient([gemini]).generate(
        "system", "attack the plan", ShelterOffline, allowed={"shelter_id": ["A", "B"]}
    )

    shelter_id = gemini.calls[0]["json_schema"]["properties"]["shelter_id"]
    assert shelter_id == {"type": "string", "enum": ["A", "B"]}


def test_an_answer_outside_the_allowed_values_is_invalid():
    outside = json.dumps({"type": "shelter_offline", "shelter_id": "E Demo Elementary School"})
    client = GemmaClient([FakeProvider("gemini", outside, outside)])

    with pytest.raises(GenerationFailed, match="shelter_id"):
        client.generate("system", "attack", ShelterOffline, allowed={"shelter_id": ["A", "B"]})


def test_reports_why_earlier_providers_were_skipped():
    client = GemmaClient(
        [FakeProvider("gemini", RateLimited("429")), FakeProvider("openrouter", VALID_ATTACK)]
    )

    generation = client.generate("system", "attack the plan", ShelterOffline)

    assert generation.skipped == ["gemini: RateLimited: 429"]


def test_sends_a_union_as_plain_variants_without_references():
    gemini = FakeProvider("gemini", VALID_ATTACK)

    GemmaClient([gemini]).generate("system", "attack", Attack, allowed={"shelter_id": ["A"]})

    schema = gemini.calls[0]["json_schema"]
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text and "discriminator" not in text
    assert "oneOf" not in text
    variants = {v["properties"]["type"]["enum"][0]: v for v in schema["anyOf"]}
    assert set(variants) == {
        "shelter_offline",
        "road_closed",
        "budget_cut",
    }
    assert variants["shelter_offline"]["properties"]["shelter_id"] == {
        "type": "string",
        "enum": ["A"],
    }
