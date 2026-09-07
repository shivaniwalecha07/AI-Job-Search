"""Resume<->job matching (see ARCHITECTURE.md 9).

Deterministic and offline: rule-based sub-scores + lexical skill overlap. Embeddings are an
optional enhancement (LLMProvider.embed) — not required to run. Never invents experience:
strengths/resume_opportunities are drawn only from skills the profile actually lists.
"""
from __future__ import annotations

import re
from typing import Any

from job_agent.schemas.core import JobMatch

_WORD = re.compile(r"[a-z0-9+#.]+")

# Domain buckets for the domain sub-score; matched against job text and target roles.
_DOMAINS = {
    "backend": ["backend", "back end", "server", "distributed", "api", "microservice"],
    "ml": ["ml", "machine learning", "ai", "deep learning", "nlp", "llm", "data scien"],
    "fullstack": ["full stack", "fullstack", "full-stack", "frontend", "front end", "react"],
    "data": ["data engineer", "data pipeline", "etl", "analytics", "spark"],
    "systems": ["systems", "infrastructure", "platform", "cloud", "devops", "sre"],
}


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in (haystack or "").lower()


def role_match_score(title: str, target_roles: list[str]) -> int:
    """Max token-overlap (Jaccard-ish) of the job title against any target role."""
    if not target_roles:
        return 60
    t = _tokens(title)
    if not t:
        return 0
    best = 0.0
    for role in target_roles:
        r = _tokens(role)
        if not r:
            continue
        overlap = len(t & r) / len(r)  # how much of the target role the title covers
        best = max(best, overlap)
    return int(round(min(1.0, best) * 100))


def company_preference_score(company: str, target_companies: list[str]) -> int:
    if not target_companies:
        return 0
    for c in target_companies:
        if _contains(company, c) or _contains(c, company):
            return 100
    return 0


def _job_text(job: dict[str, Any]) -> str:
    parts = [
        job.get("title") or "",
        job.get("description") or "",
        " ".join(job.get("required_qualifications") or []),
        " ".join(job.get("preferred_qualifications") or []),
    ]
    return " ".join(parts)


def _technical(job: dict[str, Any], skills: set[str]) -> tuple[int, list[str], list[str]]:
    text = _job_text(job)
    has_desc = bool(job.get("description"))
    matched = sorted({s for s in skills if s and _contains(text, s)})
    if not has_desc:
        # Title-only source (e.g. GitHub lists): can't assess depth. Neutral, flagged.
        base = 60 + min(20, 10 * len(matched))
        gap = ["No job description available to assess technical depth"]
        return min(base, 90), matched, gap
    if not skills:
        return 50, matched, ["No skills in profile to match against"]
    score = int(round(100 * len(matched) / max(3, len(skills))))
    score = max(30, min(100, score if matched else 30))
    gaps: list[str] = []
    if not matched:
        gaps.append("None of your listed skills appear in the description")
    return score, matched, gaps


def _domain(job: dict[str, Any], target_roles: list[str]) -> int:
    text = (_job_text(job) + " " + " ".join(target_roles)).lower()
    hits = sum(1 for kws in _DOMAINS.values() if any(k in text for k in kws))
    if hits == 0:
        return 60
    return min(100, 50 + 15 * hits)


def _location(job: dict[str, Any], prefs: dict[str, Any]) -> tuple[int, list[str]]:
    preferred = [p.lower() for p in (prefs.get("locations_preferred") or [])]
    arrangement = [a.lower() for a in (prefs.get("arrangement") or [])]
    loc = (job.get("location") or "").lower()
    remote_mode = (job.get("remote_mode") or "").lower()
    if not loc and not remote_mode:
        return 60, []
    if "remote" in loc or remote_mode == "remote":
        return (100 if "remote" in arrangement or not arrangement else 70), []
    for p in preferred:
        if p and p in loc:
            return 100, []
    return 50, ["Location not in your preferred list"]


def _employment_scores(job: dict[str, Any], prefs: dict[str, Any]) -> tuple[int, int]:
    """(experience, seniority) based on internship/full-time alignment."""
    wanted = [w.lower() for w in (prefs.get("employment_type") or [])]
    etype = (job.get("employment_type") or "").lower()
    if etype and wanted and etype in wanted:
        return 90, 90
    if etype and wanted and etype not in wanted:
        return 55, 45
    return 75, 75  # unknown employment type -> neutral


def match(job: dict[str, Any], profile: dict[str, Any], target_roles: list[str] | None = None) -> JobMatch:
    prefs = profile.get("preferences", {}) or {}
    target_roles = target_roles or []
    skills = set()
    _sk = profile.get("skills", {}) or {}
    for group in ("languages", "frameworks", "cloud", "other"):
        for item in _sk.get(group, []) or []:
            skills.add(str(item).strip().lower())

    technical, matched_skills, tech_gaps = _technical(job, skills)
    domain = _domain(job, target_roles)
    location, loc_gaps = _location(job, prefs)
    experience, seniority = _employment_scores(job, prefs)
    education = 90 if profile.get("education") else 70

    overall = int(round(
        0.30 * technical + 0.20 * domain + 0.15 * experience
        + 0.15 * education + 0.10 * location + 0.10 * seniority
    ))

    strengths = [f"Skill match: {s}" for s in matched_skills[:6]]
    if experience >= 90:
        strengths.append("Internship aligns with your stated preference")
    resume_opportunities = (
        [f"Emphasize: {', '.join(matched_skills[:6])}"] if matched_skills else []
    )

    return JobMatch(
        overall=overall, technical=technical, experience=experience, education=education,
        domain=domain, location=location, authorization=50, seniority=seniority,
        strengths=strengths, gaps=tech_gaps + loc_gaps, resume_opportunities=resume_opportunities,
    )
