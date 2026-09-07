"""Suggest ranking-weight adjustments from decision history (see ARCHITECTURE.md 25).

Signal: applications you advanced (SHORTLISTED..OFFER) are POSITIVE; WITHDRAWN/REJECTED are
NEGATIVE. For each ranking factor we compare its average contribution in positive vs negative
jobs; factors that drove jobs you liked get nudged up, others down. Bounded, renormalized,
and never applied automatically.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from job_agent.db.base import get_session
from job_agent.db.models import Application, JobMatch
from job_agent.ranking.ranker import FACTORS, load_weights
from job_agent.settings import get_settings

POSITIVE = {"SHORTLISTED", "READY_TO_APPLY", "APPLICATION_IN_PROGRESS", "AWAITING_REVIEW",
            "APPROVED", "SUBMITTED", "INTERVIEW", "OFFER"}
NEGATIVE = {"WITHDRAWN", "REJECTED"}

LEARNING_RATE = 0.05
MIN_POSITIVE = 3
MIN_NEGATIVE = 1
HISTORY_PATH = Path("config/ranking.history.jsonl")


def _avg_components(session, statuses: set[str]) -> tuple[dict[str, float], int]:
    rows = session.execute(
        select(JobMatch.rank_components_json)
        .join(Application, Application.job_id == JobMatch.job_id)
        .where(Application.status.in_(statuses))
    ).all()
    sums: dict[str, float] = {f: 0.0 for f in FACTORS}
    n = 0
    for (js,) in rows:
        comp = json.loads(js or "{}")
        if not comp:
            continue
        n += 1
        for f in FACTORS:
            sums[f] += float(comp.get(f, 0.0))
    if n:
        for f in FACTORS:
            sums[f] /= n
    return sums, n


def analyze(config_path: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    weights = load_weights(config_path or settings.ranking_config).get("weights", {})

    with get_session() as session:
        pos_avg, n_pos = _avg_components(session, POSITIVE)
        neg_avg, n_neg = _avg_components(session, NEGATIVE)

    if n_pos < MIN_POSITIVE or n_neg < MIN_NEGATIVE:
        return {
            "status": "insufficient_data", "n_positive": n_pos, "n_negative": n_neg,
            "message": f"Need >= {MIN_POSITIVE} positive and >= {MIN_NEGATIVE} negative decisions "
                       f"(have {n_pos}/{n_neg}). Shortlist/reject a few more, then re-run.",
            "current_weights": weights,
        }

    gaps = {f: pos_avg[f] - neg_avg[f] for f in FACTORS}
    max_abs = max((abs(g) for g in gaps.values()), default=0.0) or 1.0

    proposed: dict[str, float] = {}
    for f in FACTORS:
        delta = LEARNING_RATE * (gaps[f] / max_abs)
        proposed[f] = min(0.60, max(0.01, float(weights.get(f, 0.0)) + delta))
    total = sum(proposed.values()) or 1.0
    proposed = {f: round(v / total, 4) for f, v in proposed.items()}

    ranked_gaps = sorted(gaps.items(), key=lambda kv: kv[1], reverse=True)
    rationale = "; ".join(
        f"{f} {'↑' if gaps[f] > 0 else '↓'} (Δcontrib {gaps[f]:+.1f})"
        for f, _ in ranked_gaps if abs(gaps[f]) > 0.5
    ) or "No strong signal; changes are minor."

    suggestion = {
        "status": "ok", "at": datetime.now(timezone.utc).isoformat(),
        "n_positive": n_pos, "n_negative": n_neg,
        "current_weights": {f: float(weights.get(f, 0.0)) for f in FACTORS},
        "proposed_weights": proposed, "rationale": rationale,
    }
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(suggestion) + "\n")
    return suggestion


def apply_weights(proposed: dict[str, float], config_path: str | None = None) -> str:
    """Apply proposed weights, backing up the current file first (reversible)."""
    path = Path(config_path or get_settings().ranking_config)
    current = load_weights(path)
    backup = path.with_suffix(".yaml.bak")
    backup.write_text(yaml.safe_dump(current), encoding="utf-8")
    current["weights"] = proposed
    path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")
    return str(backup)
