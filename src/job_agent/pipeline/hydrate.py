"""Hydration stage (see ARCHITECTURE.md 8): backfill full JD text for already-discovered jobs
from ATS public APIs. Runs before enrich so sponsorship + matching have real text.

Polite by design: one shared client, a small inter-call delay, a per-run cap, and per-job
error isolation. Only jobs missing a description and pointing at a supported ATS are fetched.
"""
from __future__ import annotations

import time

import httpx
from sqlalchemy import or_, select

from job_agent.connectors.ats_fetch import SUPPORTED, fetch_description
from job_agent.db.base import get_session
from job_agent.db.models import Job
from job_agent.observability import get_logger
from job_agent.settings import get_settings

log = get_logger(__name__)


def run_hydrate(limit: int | None = None, delay: float | None = None) -> dict[str, int]:
    settings = get_settings()
    limit = limit if limit is not None else settings.ats_hydrate_limit
    delay = delay if delay is not None else settings.ats_hydrate_delay

    counts = {"candidates": 0, "hydrated": 0, "failed": 0}
    client = httpx.Client(timeout=20, follow_redirects=True,
                          headers={"User-Agent": "job-agent/0.1 (personal job search)"})
    try:
        with get_session() as session:
            stmt = (
                select(Job)
                .where(Job.ats.in_(list(SUPPORTED)))
                .where(Job.apply_url.is_not(None))
                .where(or_(Job.description.is_(None), Job.description == ""))
                .order_by(Job.first_seen_at.desc())
                .limit(limit)
            )
            jobs = session.scalars(stmt).all()
            counts["candidates"] = len(jobs)

            for job in jobs:
                desc = fetch_description(job.apply_url, job.ats, client=client)
                if desc:
                    job.description = desc
                    counts["hydrated"] += 1
                else:
                    counts["failed"] += 1
                if delay:
                    time.sleep(delay)
    finally:
        client.close()

    log.info("hydrate_done", **counts)
    return counts
