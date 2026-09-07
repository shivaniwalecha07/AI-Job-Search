"""Application state machine (see ARCHITECTURE.md 11). Implemented + tested.

Agents may only advance a job UP TO awaiting_review. The transitions into APPROVED and
SUBMITTED require actor='human' — this is where the human-in-the-loop guarantee is enforced.
"""
from __future__ import annotations

from enum import Enum


class ApplicationStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUALIFIED = "QUALIFIED"
    SHORTLISTED = "SHORTLISTED"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLICATION_IN_PROGRESS = "APPLICATION_IN_PROGRESS"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    REJECTED = "REJECTED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    WITHDRAWN = "WITHDRAWN"


S = ApplicationStatus

ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    S.DISCOVERED: {S.QUALIFIED, S.WITHDRAWN},
    S.QUALIFIED: {S.SHORTLISTED, S.WITHDRAWN},
    S.SHORTLISTED: {S.READY_TO_APPLY, S.WITHDRAWN},
    S.READY_TO_APPLY: {S.APPLICATION_IN_PROGRESS, S.WITHDRAWN},
    S.APPLICATION_IN_PROGRESS: {S.AWAITING_REVIEW, S.WITHDRAWN},
    S.AWAITING_REVIEW: {S.APPROVED, S.APPLICATION_IN_PROGRESS, S.REJECTED},
    S.APPROVED: {S.SUBMITTED, S.WITHDRAWN},
    S.SUBMITTED: {S.INTERVIEW, S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW: {S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.OFFER: {S.WITHDRAWN},
    S.REJECTED: set(),
    S.WITHDRAWN: set(),
}

# Transitions only a human may perform. Agents attempting these must be refused.
HUMAN_ONLY_TARGETS: set[ApplicationStatus] = {S.APPROVED, S.SUBMITTED}


def can_transition(
    current: ApplicationStatus, target: ApplicationStatus, *, actor: str
) -> bool:
    """actor is 'human' or 'agent'. Agents can never reach APPROVED/SUBMITTED."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        return False
    if target in HUMAN_ONLY_TARGETS and actor != "human":
        return False
    return True
