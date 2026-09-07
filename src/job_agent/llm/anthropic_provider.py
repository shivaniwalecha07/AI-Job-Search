"""Default LLMProvider backed by the Anthropic Claude API.

Embeddings: Anthropic does not serve embeddings directly; wire a dedicated embeddings
backend (e.g. Voyage) in `embed()`. Left as a clearly-marked TODO for Phase 1.
"""
from __future__ import annotations

import json
from typing import Type, TypeVar

from pydantic import BaseModel

from job_agent.settings import get_settings

T = TypeVar("T", bound=BaseModel)


class AnthropicProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.llm_model
        self._client = None  # lazy — don't require a key just to import

    def _get_client(self):
        if self._client is None:
            import anthropic  # imported lazily

            if not self._api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set (.env).")
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        client = self._get_client()
        msg = client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")

    def extract(self, prompt: str, schema: Type[T], *, system: str | None = None) -> T:
        instruction = (
            f"{prompt}\n\nRespond with ONLY valid JSON matching this schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        raw = self.complete(instruction, system=system)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return schema.model_validate_json(raw)

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "Wire an embeddings backend (e.g. Voyage) here — Phase 1. See ARCHITECTURE.md 9."
        )
