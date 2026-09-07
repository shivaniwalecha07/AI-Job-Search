"""Select the LLMProvider from config. Swap providers without touching agent code."""
from __future__ import annotations

from functools import lru_cache

from job_agent.llm.base import LLMProvider
from job_agent.settings import get_settings


@lru_cache
def get_llm() -> LLMProvider:
    provider = get_settings().llm_provider.lower()
    if provider == "anthropic":
        from job_agent.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if provider == "bedrock":
        raise NotImplementedError("BedrockProvider not implemented yet (see ARCHITECTURE.md 15).")
    if provider == "openai":
        raise NotImplementedError("OpenAIProvider not implemented yet (see ARCHITECTURE.md 15).")
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")
