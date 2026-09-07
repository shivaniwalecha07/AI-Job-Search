"""Feedback loop (Phase 4): learn weights from your shortlist/reject decisions.

Transparent + reversible by design (ARCHITECTURE.md 25): it only *suggests* weight changes
with an explicit rationale and appends them to a history log. Applying is a separate, opt-in
step that backs up the previous weights first.
"""
from job_agent.feedback.analyzer import analyze, apply_weights

__all__ = ["analyze", "apply_weights"]
