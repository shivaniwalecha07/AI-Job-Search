"""Tier-A official sponsorship data (see ARCHITECTURE.md 6).

Authoritative public sources (download separately; slow-changing, cache locally):
  * USCIS H-1B Employer Data Hub  https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
  * DOL OFLC disclosure data       https://www.dol.gov/agencies/eta/foreign-labor/performance

This module reads a LOCAL cache if present at data/h1b/employers.csv with columns:
    employer, fiscal_year, initial_approvals, continuing_approvals
No dataset is bundled — with no cache file, this returns [] (never fabricated). Populate the
cache from the official sources above to enable historical evidence.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from job_agent.schemas.core import ClaimType, SponsorshipEvidence

CACHE_PATH = Path("data/h1b/employers.csv")
USCIS_URL = "https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub"

_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|gmbh|plc)\b\.?", re.IGNORECASE)
_NONALNUM = re.compile(r"[^a-z0-9 ]+")


def _norm(name: str) -> str:
    v = _NONALNUM.sub(" ", (name or "").lower())
    v = _SUFFIX.sub("", v)
    return re.sub(r"\s+", " ", v).strip()


@lru_cache
def _load_cache(path: str) -> dict[str, list[dict]]:
    p = Path(path)
    table: dict[str, list[dict]] = {}
    if not p.exists():
        return table
    with open(p, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = _norm(row.get("employer", ""))
            if key:
                table.setdefault(key, []).append(row)
    return table


def company_h1b_history(company_norm: str, cache_path: str | Path = CACHE_PATH) -> list[SponsorshipEvidence]:
    """Return historical H-1B evidence for a company, or [] if no local cache/match."""
    table = _load_cache(str(cache_path))
    if not table:
        return []
    rows = table.get(_norm(company_norm), [])
    if not rows:
        return []
    years = sorted({r.get("fiscal_year", "") for r in rows if r.get("fiscal_year")})
    total = 0
    for r in rows:
        for col in ("initial_approvals", "continuing_approvals"):
            try:
                total += int(float(r.get(col, 0) or 0))
            except (TypeError, ValueError):
                pass
    return [
        SponsorshipEvidence(
            claim_type=ClaimType.INFERENCE,
            confidence=0.5,
            source_type="uscis_datahub",
            source_url=USCIS_URL,
            evidence_text=f"USCIS H-1B Data Hub: ~{total} approvals across FY {', '.join(years)} "
                          f"(company-level, full-time; historical).",
            is_historical=True,
        )
    ]
