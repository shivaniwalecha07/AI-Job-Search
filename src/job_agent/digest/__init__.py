"""Daily digest builder + email sender."""
from job_agent.digest.builder import build_digest, collect_top, generate_and_send

__all__ = ["build_digest", "collect_top", "generate_and_send"]
