"""Enrichment stage (see ARCHITECTURE.md 3): sponsorship + match + rank over stored jobs,
persisting SponsorshipAssessment, SponsorshipEvidence, and JobMatch (with final_score +
component breakdown). Deterministic; no external keys required.
"""
from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from job_agent.db.base import get_session
from job_agent.db.models import (
    Company,
    Job,
    JobMatch as JobMatchRow,
    SponsorshipAssessment as SponsorshipRow,
    SponsorshipEvidence as EvidenceRow,
)
from job_agent.matching.matcher import company_preference_score, match, role_match_score
from job_agent.observability import get_logger
from job_agent.profile import bootstrap_candidate, load_profile
from job_agent.ranking.ranker import RankInputs, load_weights, rank
from job_agent.settings import get_settings
from job_agent.sponsorship.assessor import assess
from job_agent.sponsorship.sources import company_h1b_history

log = get_logger(__name__)


def _job_dict(job: Job) -> dict:
    return {
        "title": job.title,
        "description": job.description,
        "employment_type": job.employment_type,
        "location": job.location,
        "remote_mode": job.remote_mode,
        "source_url": job.source_url,
        "apply_url": job.apply_url,
        "required_qualifications": [],
        "preferred_qualifications": [],
    }


def _upsert_sponsorship(session: Session, job: Job, assessment) -> None:
    row = session.scalar(select(SponsorshipRow).where(SponsorshipRow.job_id == job.id))
    if row is None:
        row = SponsorshipRow(job_id=job.id)
        session.add(row)
    row.status = assessment.status.value
    row.claim_type = assessment.claim_type.value
    row.confidence = assessment.confidence
    row.reason = assessment.reason
    row.needs_human_verification = assessment.needs_human_verification

    session.execute(delete(EvidenceRow).where(EvidenceRow.job_id == job.id))
    for ev in assessment.evidence:
        session.add(EvidenceRow(
            job_id=job.id, company_id=job.company_id, is_historical=ev.is_historical,
            claim_type=ev.claim_type.value, confidence=ev.confidence,
            source_url=ev.source_url, source_type=ev.source_type,
            evidence_text=ev.evidence_text, collected_at=ev.collected_at,
        ))


def _upsert_match(session: Session, job: Job, candidate_id: int, m, ranked) -> None:
    row = session.scalar(
        select(JobMatchRow).where(JobMatchRow.job_id == job.id, JobMatchRow.candidate_id == candidate_id)
    )
    if row is None:
        row = JobMatchRow(job_id=job.id, candidate_id=candidate_id)
        session.add(row)
    row.overall, row.technical, row.experience = m.overall, m.technical, m.experience
    row.education, row.domain, row.location = m.education, m.domain, m.location
    row.authorization, row.seniority = m.authorization, m.seniority
    row.strengths_json = json.dumps(m.strengths)
    row.gaps_json = json.dumps(m.gaps)
    row.resume_opportunities_json = json.dumps(m.resume_opportunities)
    row.final_score = ranked.final_score
    row.rank_components_json = json.dumps(ranked.components)


def run_enrich(config_path: str | None = None) -> dict[str, int]:
    settings = get_settings()
    profile = load_profile()
    weights = load_weights(settings.ranking_config)

    # Target roles come from the sources config.
    from job_agent.pipeline.stages import load_source_config
    sources_cfg = load_source_config(config_path)
    roles = list(sources_cfg.get("target_roles") or [])
    target_companies = (profile.get("preferences", {}) or {}).get("target_companies", []) or []

    counts = {"jobs": 0, "scored": 0, "sponsor_unknown": 0, "needs_verification": 0}

    with get_session() as session:
        candidate = bootstrap_candidate(session, profile)
        rows = session.execute(select(Job, Company).join(Company, Job.company_id == Company.id)).all()
        counts["jobs"] = len(rows)

        for job, company in rows:
            jd = _job_dict(job)
            history = company_h1b_history(company.name_norm)
            assessment = assess(jd, company_h1b_history=history)
            _upsert_sponsorship(session, job, assessment)
            if assessment.status.value == "UNKNOWN":
                counts["sponsor_unknown"] += 1
            if assessment.needs_human_verification:
                counts["needs_verification"] += 1

            m = match(jd, profile, roles)
            m.authorization = _auth_from_status(assessment.status.value)
            ranked = rank(
                RankInputs(
                    job_id=str(job.id), match=m, sponsorship=assessment,
                    role_match=role_match_score(job.title, roles),
                    company_preference=company_preference_score(company.name, target_companies),
                    posting_date=job.posting_date,
                ),
                weights,
            )
            _upsert_match(session, job, candidate.id, m, ranked)
            counts["scored"] += 1

    log.info("enrich_done", **counts)
    return counts


def _auth_from_status(status: str) -> int:
    return {
        "YES": 100, "COMPANY_SPECIFIC": 70, "JOB_SPECIFIC": 60,
        "UNCLEAR": 50, "UNKNOWN": 40, "NO": 0,
    }.get(status, 40)
