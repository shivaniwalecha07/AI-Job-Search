"""Normalization + deduplication."""
from job_agent.normalize.dedup import compute_dedup_key, normalize_text
from job_agent.normalize.normalizer import classify_freshness, normalize

__all__ = ["compute_dedup_key", "normalize_text", "normalize", "classify_freshness"]
