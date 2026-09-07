"""Stage orchestration (see ARCHITECTURE.md 3, 13, 21).

Two lanes:
  * unattended (supervised=False): only connectors with requires_supervision=False -> cron-safe
  * supervised  (supervised=True): includes LinkedIn; run only when you are present + logged in

A failing connector never aborts the run (isolated + logged). Stubbed stages are reported
rather than crashing the pipeline, so the scaffold runs end to end today.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from job_agent.connectors import build_connector
from job_agent.db.base import get_session
from job_agent.normalize.normalizer import normalize
from job_agent.observability import get_logger
from job_agent.pipeline.persist import upsert_jobs
from job_agent.schemas.core import NormalizedJob, RawJobRecord
from job_agent.settings import get_settings

log = get_logger(__name__)


def load_source_config(path: str | Path | None = None) -> dict[str, Any]:
    path = path or get_settings().target_roles_config
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_enabled_connectors(config: dict[str, Any], *, supervised: bool):
    """Return connector instances for this lane.

    Unattended lane excludes requires_supervision=True. Supervised lane includes everything
    enabled. A supervised connector never runs in the unattended lane, by construction.
    """
    connectors = []
    for c in config.get("connectors", []):
        if not c.get("enabled", False):
            continue
        needs_sup = bool(c.get("requires_supervision", False))
        if needs_sup and not supervised:
            log.info("skip_supervised_connector", source_id=c["id"], lane="unattended")
            continue
        connectors.append(
            build_connector(c["type"], c["id"], c.get("params", {}))
        )
    return connectors


def run_discovery(*, supervised: bool = False, config_path: str | None = None) -> dict[str, int]:
    settings = get_settings()
    config = load_source_config(config_path)
    connectors = build_enabled_connectors(config, supervised=supervised)
    counts = {
        "connectors": len(connectors),
        "fetched": 0,
        "normalized": 0,
        "errors": 0,
        "stubbed": 0,
        "new": 0,
        "updated": 0,
    }

    raw_records: list[RawJobRecord] = []
    for conn in connectors:
        health = conn.health()
        log.info("connector_health", source_id=conn.source_id, ok=health.ok, detail=health.detail)
        try:
            records = conn.fetch()
            counts["fetched"] += len(records)
            raw_records.extend(records)
            log.info("fetched", source_id=conn.source_id, n=len(records))
        except NotImplementedError as exc:
            counts["stubbed"] += 1
            log.warning("connector_stubbed", source_id=conn.source_id, detail=str(exc))
        except Exception as exc:  # isolate: one bad source never aborts the run
            counts["errors"] += 1
            log.error("connector_error", source_id=conn.source_id, error=str(exc))

    # Normalize (deterministic; a bad record never aborts the batch).
    normalized: list[NormalizedJob] = []
    for raw in raw_records:
        try:
            normalized.append(normalize(raw, recent_window_days=settings.recent_window_days))
        except Exception as exc:
            counts["errors"] += 1
            log.error("normalize_error", source_id=raw.source_id, error=str(exc))
    counts["normalized"] = len(normalized)

    # Dedup within this batch by dedup_key before persisting.
    by_key: dict[str, NormalizedJob] = {}
    for nj in normalized:
        by_key[nj.dedup_key] = nj
    counts["batch_deduped"] = len(normalized) - len(by_key)

    # Persist (upsert with NEW-once semantics).
    if by_key:
        with get_session() as session:
            pc = upsert_jobs(
                session, list(by_key.values()), recent_window_days=settings.recent_window_days
            )
        counts["new"] = pc.new
        counts["updated"] = pc.updated

    log.info("discovery_done", **counts, lane="supervised" if supervised else "unattended")
    return counts


def run_hydrate_stage() -> dict[str, int]:
    from job_agent.pipeline.hydrate import run_hydrate

    return run_hydrate()


def run_enrich_stage(*, config_path: str | None = None) -> dict[str, int]:
    from job_agent.pipeline.enrich import run_enrich

    return run_enrich(config_path=config_path)


def run_digest_stage() -> dict[str, Any]:
    from job_agent.digest.builder import generate_and_send

    return generate_and_send()


def run_all(*, supervised: bool = False) -> dict[str, Any]:
    return {
        "discovery": run_discovery(supervised=supervised),
        "hydrate": run_hydrate_stage(),
        "enrich": run_enrich_stage(),
        "digest": run_digest_stage(),
    }


STAGES = {
    "discovery": lambda supervised: run_discovery(supervised=supervised),
    "hydrate": lambda supervised: run_hydrate_stage(),
    "enrich": lambda supervised: run_enrich_stage(),
    "digest": lambda supervised: run_digest_stage(),
    "all": lambda supervised: run_all(supervised=supervised),
}
