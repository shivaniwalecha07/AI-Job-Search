"""Raw -> NormalizedJob mapping + freshness classification (see ARCHITECTURE.md 4.2).

Deterministic field mapping first; an LLM would be used ONLY to extract unstructured JD
fields (required/preferred quals) for sources that carry a full description — the GitHub
lists don't, so this path is pure/deterministic.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from job_agent.normalize.dedup import (
    compute_dedup_key,
    normalize_company,
    normalize_location,
    normalize_title,
)
from job_agent.schemas.core import Freshness, NormalizedJob, RawJobRecord

_INTERN_HINT = re.compile(r"\b(intern|internship|co-?op)\b", re.IGNORECASE)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def classify_freshness(posting_date: datetime | None, recent_window_days: int) -> Freshness:
    """RECENT if posted within the window; STALE if older. NEW is set by the persistence
    layer the first time a dedup_key is seen (see pipeline.persist)."""
    if posting_date is None:
        return Freshness.RECENT
    now = datetime.now(timezone.utc)
    if posting_date.tzinfo is None:
        posting_date = posting_date.replace(tzinfo=timezone.utc)
    age_days = (now - posting_date).days
    return Freshness.RECENT if age_days <= recent_window_days else Freshness.STALE


def normalize(raw: RawJobRecord, recent_window_days: int = 3) -> NormalizedJob:
    p = raw.payload
    company = p.get("company") or ""
    title = p.get("role") or ""
    location = p.get("location")
    ats_job_id = p.get("ats_job_id")
    apply_url = p.get("apply_url")
    posting_date = _parse_dt(p.get("posting_date"))

    employment_type = "internship" if _INTERN_HINT.search(title) else None
    source_url = apply_url or p.get("company_url") or raw.raw_url

    return NormalizedJob(
        dedup_key=compute_dedup_key(company, ats_job_id, title, location),
        title=title,
        title_norm=normalize_title(title),
        company=company,
        company_norm=normalize_company(company),
        location=location,
        location_norm=normalize_location(location),
        employment_type=employment_type,
        posting_date=posting_date,
        ats=p.get("ats"),
        apply_url=apply_url,
        source_url=source_url,
        source_id=raw.source_id,
        freshness=classify_freshness(posting_date, recent_window_days),
    )
