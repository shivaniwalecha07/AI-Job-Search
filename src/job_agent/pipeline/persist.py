"""Persist NormalizedJobs into the DB with dedup + NEW-once semantics (ARCHITECTURE.md 4.2).

A job is inserted once (freshness=NEW). On a later scan the same dedup_key is found and only
last_seen_at + volatile fields update; freshness is recomputed to RECENT/STALE so we never
re-notify about a job as if it were new.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.db.models import Company, Job
from job_agent.normalize.normalizer import classify_freshness
from job_agent.schemas.core import Freshness, NormalizedJob


@dataclass
class PersistCounts:
    new: int = 0
    updated: int = 0
    companies_created: int = 0
    new_titles: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {"new": self.new, "updated": self.updated, "companies_created": self.companies_created}


def _get_or_create_company(session: Session, name: str, name_norm: str) -> tuple[Company, bool]:
    company = session.scalar(select(Company).where(Company.name_norm == name_norm))
    if company:
        return company, False
    company = Company(name=name, name_norm=name_norm)
    session.add(company)
    session.flush()  # assign id
    return company, True


def upsert_jobs(
    session: Session, jobs: list[NormalizedJob], *, recent_window_days: int = 3
) -> PersistCounts:
    counts = PersistCounts()
    now = datetime.now(timezone.utc)

    for nj in jobs:
        company, created = _get_or_create_company(session, nj.company, nj.company_norm)
        if created:
            counts.companies_created += 1

        existing = session.scalar(select(Job).where(Job.dedup_key == nj.dedup_key))
        if existing is None:
            session.add(
                Job(
                    dedup_key=nj.dedup_key,
                    company_id=company.id,
                    ats_job_id=None,  # id is folded into dedup_key at normalization time
                    title=nj.title,
                    title_norm=nj.title_norm,
                    location=nj.location,
                    location_norm=nj.location_norm,
                    remote_mode=nj.remote_mode,
                    employment_type=nj.employment_type,
                    posting_date=nj.posting_date,
                    first_seen_at=now,
                    last_seen_at=now,
                    ats=nj.ats,
                    apply_url=nj.apply_url,
                    source_url=nj.source_url,
                    source_id=nj.source_id,
                    freshness=Freshness.NEW.value,
                )
            )
            counts.new += 1
            counts.new_titles.append(f"{nj.company} — {nj.title}")
        else:
            existing.last_seen_at = now
            existing.apply_url = nj.apply_url or existing.apply_url
            existing.location = nj.location or existing.location
            # No longer NEW: recompute freshness from age.
            existing.freshness = classify_freshness(nj.posting_date, recent_window_days).value
            counts.updated += 1

    return counts
