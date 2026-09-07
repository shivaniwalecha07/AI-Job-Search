"""The human-in-the-loop guarantee, enforced as tests."""
from job_agent.application.states import ApplicationStatus as S
from job_agent.application.states import can_transition


def test_agent_cannot_approve():
    assert not can_transition(S.AWAITING_REVIEW, S.APPROVED, actor="agent")


def test_agent_cannot_submit():
    assert not can_transition(S.APPROVED, S.SUBMITTED, actor="agent")


def test_human_can_approve_and_submit():
    assert can_transition(S.AWAITING_REVIEW, S.APPROVED, actor="human")
    assert can_transition(S.APPROVED, S.SUBMITTED, actor="human")


def test_agent_can_advance_up_to_awaiting_review():
    assert can_transition(S.APPLICATION_IN_PROGRESS, S.AWAITING_REVIEW, actor="agent")


def test_illegal_jump_rejected():
    assert not can_transition(S.DISCOVERED, S.SUBMITTED, actor="human")


def test_terminal_states_have_no_exits():
    assert not can_transition(S.REJECTED, S.INTERVIEW, actor="human")
