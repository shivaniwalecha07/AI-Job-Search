"""Deduplication (see ARCHITECTURE.md 4.2). Pure functions, no external deps — fully tested.

Primary dedup key:  company_norm + ats_job_id
Fallback key:       company_norm + title_norm + location_norm
A job is 'NEW' only once; re-seeing it updates last_seen_at without re-notifying.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_NONALNUM = re.compile(r"[^a-z0-9 ]+")

# Common company suffixes stripped so "Stripe, Inc." == "Stripe".
_COMPANY_SUFFIXES = (
    " inc", " inc.", " llc", " l.l.c", " ltd", " limited", " corp", " corporation",
    " co", " company", " gmbh", " plc",
)

# Title noise removed so "Software Engineer Intern (Summer 2027)" normalizes cleanly.
_TITLE_NOISE = (
    "summer", "fall", "spring", "winter", "2024", "2025", "2026", "2027", "2028",
    "intern", "internship", "co-op", "coop",
)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    v = value.strip().lower()
    v = _NONALNUM.sub(" ", v)
    v = _WS.sub(" ", v).strip()
    return v


def normalize_company(name: str | None) -> str:
    v = normalize_text(name)
    for suffix in _COMPANY_SUFFIXES:
        if v.endswith(suffix):
            v = v[: -len(suffix)].strip()
    return v


def normalize_title(title: str | None) -> str:
    v = normalize_text(title)
    tokens = [t for t in v.split() if t not in _TITLE_NOISE]
    return " ".join(tokens)


def normalize_location(location: str | None) -> str:
    return normalize_text(location)


def compute_dedup_key(
    company: str | None,
    ats_job_id: str | None = None,
    title: str | None = None,
    location: str | None = None,
) -> str:
    """Primary key when ats_job_id is present; otherwise the fuzzy fallback key."""
    company_norm = normalize_company(company)
    if ats_job_id:
        return f"{company_norm}|id:{ats_job_id.strip().lower()}"
    return f"{company_norm}|t:{normalize_title(title)}|l:{normalize_location(location)}"
