"""Application prep + human-in-the-loop lifecycle (Phase 2)."""
from job_agent.application.states import ALLOWED_TRANSITIONS, ApplicationStatus, can_transition

__all__ = ["ALLOWED_TRANSITIONS", "ApplicationStatus", "can_transition"]
