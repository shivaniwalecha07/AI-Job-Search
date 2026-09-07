"""Swappable LLM layer. Agents depend on LLMProvider, never on a vendor SDK directly."""
from job_agent.llm.base import LLMProvider
from job_agent.llm.factory import get_llm

__all__ = ["LLMProvider", "get_llm"]
