"""Application lifecycle service (see ARCHITECTURE.md 11). Every transition is validated by
the state machine and written to the append-only ApplicationEvent audit log. Agents can only
reach AWAITING_REVIEW; APPROVED/SUBMITTED require actor='human'.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.application.states import ALLOWED_TRANSITIONS, ApplicationStatus, can_transition
from job_agent.db.models import (
    Application,
    ApplicationAnswer,
    ApplicationEvent,
    Candidate,
    Company,
    Job,
    JobMatch,
    SponsorshipAssessment,
)


def get_or_create_application(session: Session, job_id: int, candidate_id: int) -> Application:
    app = session.scalar(
        select(Application).where(Application.job_id == job_id, Application.candidate_id == candidate_id)
    )
    if app is None:
        app = Application(job_id=job_id, candidate_id=candidate_id, status=ApplicationStatus.DISCOVERED.value)
        session.add(app)
        session.flush()
        _log(session, app, None, ApplicationStatus.DISCOVERED, "agent", "application created")
    return app


def _log(session: Session, app: Application, frm, to, actor: str, detail: str) -> None:
    session.add(ApplicationEvent(
        application_id=app.id, at=datetime.now(timezone.utc), actor=actor,
        from_status=(frm.value if hasattr(frm, "value") else frm),
        to_status=(to.value if hasattr(to, "value") else to), detail=detail,
    ))


def transition(session: Session, app: Application, target: ApplicationStatus, *, actor: str, detail: str = "") -> bool:
    current = ApplicationStatus(app.status)
    if not can_transition(current, target, actor=actor):
        return False
    _log(session, app, current, target, actor, detail or f"{current.value} -> {target.value}")
    app.status = target.value
    if target == ApplicationStatus.SUBMITTED:
        app.applied_at = datetime.now(timezone.utc)
    return True


def _path(start: ApplicationStatus, goal: ApplicationStatus, actor: str) -> list[ApplicationStatus] | None:
    """Shortest sequence of valid transitions from start to goal for this actor."""
    if start == goal:
        return []
    seen = {start}
    queue: deque[tuple[ApplicationStatus, list[ApplicationStatus]]] = deque([(start, [])])
    while queue:
        node, path = queue.popleft()
        for nxt in ALLOWED_TRANSITIONS.get(node, set()):
            if nxt in seen or not can_transition(node, nxt, actor=actor):
                continue
            if nxt == goal:
                return path + [nxt]
            seen.add(nxt)
            queue.append((nxt, path + [nxt]))
    return None


def advance_to(session: Session, app: Application, target: ApplicationStatus, *, actor: str, detail: str = "") -> bool:
    """Step through the allowed path to reach `target` (e.g. DISCOVERED -> SHORTLISTED)."""
    path = _path(ApplicationStatus(app.status), target, actor)
    if path is None:
        return False
    for step in path:
        transition(session, app, step, actor=actor, detail=detail)
    return True


def shortlist_jobs(session: Session, job_ids: list[int], candidate_id: int) -> list[int]:
    done = []
    for jid in job_ids:
        job = session.get(Job, jid)
        if not job:
            continue
        app = get_or_create_application(session, jid, candidate_id)
        if advance_to(session, app, ApplicationStatus.SHORTLISTED, actor="human", detail="shortlisted"):
            done.append(jid)
    return done


def get_candidate(session: Session) -> Candidate | None:
    return session.scalar(select(Candidate).limit(1))


def prepare_applications(session: Session, job_ids: list[int], candidate_id: int, profile: dict) -> list[dict]:
    """Build an ApplicationPackage per job, persist it, and advance to AWAITING_REVIEW.
    Never goes past AWAITING_REVIEW — approval/submission are human-only."""
    from job_agent.application.prep import prepare

    results = []
    for jid in job_ids:
        row = session.execute(
            select(Job, Company, JobMatch, SponsorshipAssessment)
            .join(Company, Job.company_id == Company.id)
            .outerjoin(JobMatch, JobMatch.job_id == Job.id)
            .outerjoin(SponsorshipAssessment, SponsorshipAssessment.job_id == Job.id)
            .where(Job.id == jid)
        ).first()
        if not row:
            continue
        job, company, m, spon = row
        job_dict = {
            "id": job.id, "title": job.title, "company": company.name,
            "description": job.description, "employment_type": job.employment_type,
        }
        pkg = prepare(
            job_dict, profile,
            sponsorship_status=(spon.status if spon else "UNKNOWN"),
            match_overall=(m.overall if m else None),
        )
        app = get_or_create_application(session, jid, candidate_id)
        advance_to(session, app, ApplicationStatus.AWAITING_REVIEW, actor="agent", detail="package prepared")
        app.cover_letter = pkg.cover_letter
        app.notes = f"resume_version={pkg.resume_version}; concerns={'; '.join(pkg.concerns)}"

        session.query(ApplicationAnswer).filter(ApplicationAnswer.application_id == app.id).delete()
        for ans in pkg.answers:
            session.add(ApplicationAnswer(
                application_id=app.id, question=ans.question,
                classification=ans.classification.value,
                draft_answer=ans.draft_answer, source_note=ans.source_note,
            ))
        results.append({"job_id": jid, "app_id": app.id, "questions_for_you": pkg.questions_requiring_user,
                        "concerns": pkg.concerns})
    return results
