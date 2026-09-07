"""LLMProvider protocol (see ARCHITECTURE.md 15). Structured output requested at this boundary."""
from __future__ import annotations

from typing import Protocol, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Provider contract. Concrete impls: AnthropicProvider (default), Bedrock/OpenAI later."""

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Free-text completion."""
        ...

    def extract(self, prompt: str, schema: Type[T], *, system: str | None = None) -> T:
        """Completion parsed into a Pydantic schema (structured extraction/classification)."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...
