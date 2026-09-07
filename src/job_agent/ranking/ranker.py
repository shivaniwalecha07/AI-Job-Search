"""Ranking engine (see ARCHITECTURE.md 10). Pure + deterministic + explainable.

final_score = sum(weight_i * subscore_i), each contribution stored so the digest can
show the breakdown and a human-readable rationale. No LLM, no I/O in the core function.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from job_agent.schemas.core import JobMatch, RankedJob, SponsorshipAssessment, SponsorshipStatus

# Factors and the sub-score each pulls from (0-100 scale before weighting).
FACTORS = (
    "role_match",
    "technical_match",
    "resume_match",
    "authorization_match",
    "experience_match",
    "location_match",
    "company_preference",
    "recency",
)

# Sponsorship status -> authorization sub-score (0-100). Conservative on uncertainty.
_AUTH_SCORE = {
    SponsorshipStatus.YES: 100,
    SponsorshipStatus.COMPANY_SPECIFIC: 70,
    SponsorshipStatus.JOB_SPECIFIC: 60,
    SponsorshipStatus.UNCLEAR: 50,
    SponsorshipStatus.UNKNOWN: 40,
    SponsorshipStatus.NO: 0,
}


@dataclass
class RankInputs:
    job_id: str
    match: JobMatch
    sponsorship: SponsorshipAssessment | None = None
    role_match: int = 0             # how well title matches target roles (0-100)
    company_preference: int = 0     # 0-100 from profile target_companies
    posting_date: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def load_weights(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _recency_score(posting_date: datetime | None, full_days: int, zero_days: int) -> float:
    if posting_date is None:
        return 60.0  # neutral-ish when unknown
    age_days = max(0.0, (datetime.utcnow() - posting_date).total_seconds() / 86400.0)
    if age_days <= full_days:
        return 100.0
    if age_days >= zero_days:
        return 0.0
    span = zero_days - full_days
    return round(100.0 * (1.0 - (age_days - full_days) / span), 1)


def _subscores(inp: RankInputs, recency_cfg: dict[str, Any]) -> dict[str, float]:
    m = inp.match
    auth = (
        _AUTH_SCORE.get(inp.sponsorship.status, 40) if inp.sponsorship else m.authorization
    )
    return {
        "role_match": float(inp.role_match),
        "technical_match": float(m.technical),
        "resume_match": float(m.overall),
        "authorization_match": float(auth),
        "experience_match": float(m.experience),
        "location_match": float(m.location),
        "company_preference": float(inp.company_preference),
        "recency": _recency_score(
            inp.posting_date,
            int(recency_cfg.get("full_days", 2)),
            int(recency_cfg.get("zero_days", 21)),
        ),
    }


def rank(inp: RankInputs, config: dict[str, Any]) -> RankedJob:
    weights: dict[str, float] = config.get("weights", {})
    recency_cfg: dict[str, Any] = config.get("recency", {})
    subs = _subscores(inp, recency_cfg)

    components: dict[str, float] = {}
    total = 0.0
    for factor in FACTORS:
        w = float(weights.get(factor, 0.0))
        contribution = round(w * subs[factor], 2)
        components[factor] = contribution
        total += contribution

    top = sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:3]
    rationale = "Top drivers: " + ", ".join(f"{k} (+{v:.1f})" for k, v in top if v > 0)
    if inp.sponsorship and inp.sponsorship.needs_human_verification:
        rationale += " | sponsorship needs human verification"

    return RankedJob(
        job_id=inp.job_id,
        final_score=round(total, 2),
        components=components,
        rationale=rationale or "No positive drivers",
    )
