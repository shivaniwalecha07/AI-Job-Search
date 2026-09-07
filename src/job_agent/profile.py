"""Candidate profile loading (see ARCHITECTURE.md 2). The profile holds ONLY verified facts;
nothing here is generated. Matching, ranking, and application drafting draw from it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from job_agent.settings import get_settings


def load_profile(path: str | Path | None = None) -> dict[str, Any]:
    """Load config/profile.yaml (falls back to the committed example if absent)."""
    path = Path(path or get_settings().profile_config)
    if not path.exists():
        example = path.with_name("profile.example.yaml")
        if example.exists():
            path = example
        else:
            raise FileNotFoundError(f"No profile at {path} and no profile.example.yaml alongside it.")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def profile_skills(profile: dict[str, Any]) -> set[str]:
    """Flat set of lowercased skill tokens from the profile."""
    skills = profile.get("skills", {}) or {}
    out: set[str] = set()
    for group in ("languages", "frameworks", "cloud", "other"):
        for item in skills.get(group, []) or []:
            out.add(str(item).strip().lower())
    return {s for s in out if s}


def target_roles(profile_or_sources: dict[str, Any]) -> list[str]:
    """Target roles may live in the sources config; accept either shape."""
    if "target_roles" in profile_or_sources:
        return list(profile_or_sources.get("target_roles") or [])
    return list((profile_or_sources.get("preferences", {}) or {}).get("target_roles") or [])


def bootstrap_candidate(session, profile: dict[str, Any]):
    """Create or update the single Candidate row from the profile. Returns the Candidate."""
    from sqlalchemy import select

    from job_agent.db.models import Candidate

    cand_info = profile.get("candidate", {}) or {}
    email = cand_info.get("email", "")
    name = cand_info.get("name", "")
    needs_sponsorship = bool((profile.get("work_authorization", {}) or {}).get("needs_sponsorship", False))

    candidate = session.scalar(select(Candidate).where(Candidate.email == email)) if email else None
    if candidate is None:
        candidate = Candidate(
            name=name, email=email, needs_sponsorship=needs_sponsorship,
            profile_json=json.dumps(profile),
        )
        session.add(candidate)
        session.flush()
    else:
        candidate.name = name or candidate.name
        candidate.needs_sponsorship = needs_sponsorship
        candidate.profile_json = json.dumps(profile)
    return candidate


def register_master_resume(session, candidate, profile: dict[str, Any]):
    """Create/update the master Resume row pointing at the resume file on disk."""
    from sqlalchemy import select

    from job_agent.db.models import Resume

    master_path = (profile.get("resumes", {}) or {}).get("master")
    if not master_path:
        return None
    resume = session.scalar(
        select(Resume).where(Resume.candidate_id == candidate.id, Resume.is_master == True)  # noqa: E712
    )
    if resume is None:
        resume = Resume(candidate_id=candidate.id, version="master", is_master=True)
        session.add(resume)
    resume.source_path = master_path
    resume.diff_summary = "Master resume (fixed; per-role variants generated in resumes/tailored)."
    session.flush()
    return resume
