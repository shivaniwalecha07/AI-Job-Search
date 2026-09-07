from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from job_agent.application.classify import classify_question
from job_agent.application.service import advance_to, get_or_create_application, transition
from job_agent.application.states import ApplicationStatus as S
from job_agent.db.base import Base
from job_agent.db.models import Candidate, Company, Job
from job_agent.schemas.core import QuestionClass

PROFILE = {"education": [{"degree": "MS CS", "school": "ASU", "graduation": "2027-05"}],
           "skills": {"languages": ["Python"]}}


def test_classify_sponsorship_is_must_ask():
    a = classify_question("Will you now or in the future require visa sponsorship?", PROFILE)
    assert a.classification == QuestionClass.MUST_ASK_USER
    assert a.draft_answer is None


def test_classify_motivation_is_needs_review():
    a = classify_question("Why do you want to work here?", PROFILE)
    assert a.classification == QuestionClass.NEEDS_REVIEW


def test_classify_factual_is_auto_with_source():
    a = classify_question("What is your expected graduation date?", PROFILE)
    assert a.classification == QuestionClass.AUTO_ANSWERABLE
    assert "2027" in (a.draft_answer or "")
    assert a.source_note


def _mem_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(session) -> tuple[int, int]:
    cand = Candidate(name="S", email="s@x.com", needs_sponsorship=True, profile_json="{}")
    comp = Company(name="Acme", name_norm="acme")
    session.add_all([cand, comp]); session.flush()
    job = Job(dedup_key="acme|t:swe|l:sf", company_id=comp.id, title="SWE Intern",
              title_norm="swe", source_url="http://x", source_id="github:test",
              first_seen_at=datetime.now(timezone.utc), last_seen_at=datetime.now(timezone.utc),
              freshness="NEW")
    session.add(job); session.flush()
    return job.id, cand.id


def test_agent_cannot_approve_but_human_can():
    session = _mem_session()
    job_id, cand_id = _seed(session)
    app = get_or_create_application(session, job_id, cand_id)
    assert advance_to(session, app, S.AWAITING_REVIEW, actor="agent") is True
    assert transition(session, app, S.APPROVED, actor="agent") is False   # agent blocked
    assert transition(session, app, S.APPROVED, actor="human") is True     # human allowed
    assert transition(session, app, S.SUBMITTED, actor="human") is True
    assert app.status == "SUBMITTED"


def test_shortlist_path_reaches_shortlisted():
    session = _mem_session()
    job_id, cand_id = _seed(session)
    app = get_or_create_application(session, job_id, cand_id)
    assert advance_to(session, app, S.SHORTLISTED, actor="human") is True
    assert app.status == "SHORTLISTED"
