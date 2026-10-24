"""Gemma 4 providers: OpenRouter first, the free Gemini API as a fallback.

On the Gemini API, Gemma 4 with a schema loops on long prompts (repeated words,
500 errors, RECITATION stops), so it is only the backup.

Both receive the strict JSON schema and return the raw JSON text; the client
validates it.
"""

import os
from typing import Any

import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from proofloop.gemma.client import Provider, ProviderError, RateLimited

GEMINI_MODEL = "gemma-4-26b-a4b-it"
OPENROUTER_MODEL = "google/gemma-4-26b-a4b-it"
TEMPERATURE = 0.3
# Bounds a run where constrained decoding gets stuck emitting whitespace.
MAX_OUTPUT_TOKENS = 1024
TIMEOUT_SECONDS = 60


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = GEMINI_MODEL):
        self.model = model
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000)
        )

    def complete(self, system: str, prompt: str, json_schema: dict[str, Any]) -> str:
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=json_schema,
                    temperature=TEMPERATURE,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                ),
            )
        except genai_errors.APIError as error:
            raise (RateLimited if error.code == 429 else ProviderError)(str(error)) from error
        except Exception as error:  # network failures and timeouts
            raise ProviderError(f"{type(error).__name__}: {error}") from error
        if not response.text:
            raise ProviderError("empty response")
        return response.text


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str, model: str = OPENROUTER_MODEL):
        self.model = model
        self._client = openai.OpenAI(
            api_key=api_key, base_url="https://openrouter.ai/api/v1", timeout=TIMEOUT_SECONDS
        )

    def complete(self, system: str, prompt: str, json_schema: dict[str, Any]) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "strict": True, "schema": json_schema},
                },
                temperature=TEMPERATURE,
                max_tokens=MAX_OUTPUT_TOKENS,
                # Only route to OpenRouter providers that honour the JSON schema.
                extra_body={"provider": {"require_parameters": True}},
            )
        except openai.RateLimitError as error:
            raise RateLimited(str(error)) from error
        except openai.OpenAIError as error:
            raise ProviderError(f"{type(error).__name__}: {error}") from error
        text = response.choices[0].message.content if response.choices else None
        if not text:
            raise ProviderError("empty response")
        return text


def providers_from_env() -> list[Provider]:
    """Configured providers in fallback order; keys come from the environment."""
    providers: list[Provider] = []
    if key := os.environ.get("OPENROUTER_API_KEY"):
        providers.append(OpenRouterProvider(key))
    if key := os.environ.get("GEMINI_API_KEY"):
        providers.append(GeminiProvider(key))
    return providers
