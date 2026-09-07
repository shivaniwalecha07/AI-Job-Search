"""Sponsorship assessment (see ARCHITECTURE.md 6). NEVER emits a bare 'yes'.

Combines two independent signals, kept distinct:
  (a) JD text        -> does THIS posting state a sponsorship policy?   (role-specific, FACT)
  (b) official data  -> has this COMPANY sponsored H-1B before?         (historical, INFERENCE)
Silence + uncertainty resolve to UNKNOWN/UNCLEAR with needs_human_verification=True.
Historical evidence is always labelled historical and never rendered as proof of (a).
This is an informational screen, not legal advice.
"""
from __future__ import annotations

import re

from job_agent.schemas.core import (
    ClaimType,
    SponsorshipAssessment,
    SponsorshipEvidence,
    SponsorshipStatus,
)

# Regexes over the job description. Order matters: negatives/citizenship are checked with positives
# so a conflict can be detected.
_POSITIVE = [
    r"\bwill sponsor\b",
    r"\bvisa sponsorship (is )?available\b",
    r"\bwe sponsor\b",
    r"\bopen to sponsor(ing|ship)\b",
    r"\bh-?1b sponsorship\b",
    r"\bsponsorship (is )?(available|offered|provided)\b",
]
_NEGATIVE = [
    r"\b(?:not|unable|cannot|can'?t|won'?t|will not|do not|does not|are not|is not|isn'?t|aren'?t)\b"
    r".{0,40}\bsponsor(?:ship|ing)?\b",
    r"\bwithout (?:visa )?sponsorship\b",
    r"\bno (?:visa )?sponsorship\b",
    r"\bnot (?:eligible for|require) .{0,20}sponsorship\b",
    r"\bnot require sponsorship(?: now or in the future)?\b",
    r"\bauthoriz(?:ed|ation) to work .{0,40}without (?:visa )?sponsorship\b",
]
_CITIZENSHIP = [
    r"\bu\.?s\.? citizen(ship)?\b",
    r"\bmust be a citizen\b",
    r"\bsecurity clearance\b",
    r"\bgovernment clearance\b",
    r"\bpermanent resident\b",
]


def _find(patterns: list[str], text: str) -> str | None:
    """Return the matched sentence (verbatim evidence) for the first matching pattern."""
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            start = text.rfind(".", 0, m.start()) + 1
            end = text.find(".", m.end())
            end = end if end != -1 else len(text)
            return text[start:end].strip()[:300]
    return None


def _get(job, attr: str, default=None):
    if isinstance(job, dict):
        return job.get(attr, default)
    return getattr(job, attr, default)


def assess(job, company_h1b_history: list[SponsorshipEvidence] | None = None) -> SponsorshipAssessment:
    """Assess sponsorship for a job. `job` may be a NormalizedJob, a DB Job, or a dict with
    description / employment_type / source_url / apply_url."""
    description = _get(job, "description") or ""
    employment_type = (_get(job, "employment_type") or "").lower()
    source_url = _get(job, "source_url") or _get(job, "apply_url") or ""
    history = company_h1b_history or []

    pos = _find(_POSITIVE, description)
    neg = _find(_NEGATIVE, description)
    cit = _find(_CITIZENSHIP, description)

    evidence: list[SponsorshipEvidence] = []

    def jd_ev(quote: str, ct: ClaimType, conf: float) -> SponsorshipEvidence:
        return SponsorshipEvidence(
            claim_type=ct, confidence=conf, source_type="job_description",
            source_url=source_url, evidence_text=quote, is_historical=False,
        )

    # Conflict: both a positive and a negative/citizenship signal.
    if pos and (neg or cit):
        evidence.append(jd_ev(pos, ClaimType.FACT, 0.5))
        evidence.append(jd_ev(neg or cit, ClaimType.FACT, 0.5))
        return SponsorshipAssessment(
            status=SponsorshipStatus.UNCLEAR, claim_type=ClaimType.INFERENCE, confidence=0.4,
            reason="Job description contains conflicting sponsorship signals.",
            needs_human_verification=True, evidence=evidence + list(history),
        )

    if neg:
        return SponsorshipAssessment(
            status=SponsorshipStatus.NO, claim_type=ClaimType.FACT, confidence=0.9,
            reason="Job description states sponsorship is not available.",
            needs_human_verification=False, evidence=[jd_ev(neg, ClaimType.FACT, 0.9)],
        )

    if pos:
        return SponsorshipAssessment(
            status=SponsorshipStatus.YES, claim_type=ClaimType.FACT, confidence=0.85,
            reason="Job description states sponsorship is available.",
            needs_human_verification=False, evidence=[jd_ev(pos, ClaimType.FACT, 0.85)],
        )

    if cit:
        return SponsorshipAssessment(
            status=SponsorshipStatus.NO, claim_type=ClaimType.INFERENCE, confidence=0.6,
            reason="Job requires citizenship/clearance/permanent residency, which typically "
                   "precludes visa sponsorship. Verify for this specific role.",
            needs_human_verification=True, evidence=[jd_ev(cit, ClaimType.INFERENCE, 0.6)],
        )

    # JD is silent. Fall back to company history, clearly labelled historical.
    if history:
        is_intern = "intern" in employment_type or "co-op" in employment_type
        status = SponsorshipStatus.JOB_SPECIFIC if is_intern else SponsorshipStatus.UNCLEAR
        reason = (
            "No statement in the posting. Company has historical H-1B sponsorship (full-time); "
            + ("internship eligibility is not established and must be verified."
               if is_intern else "current/role-specific policy must be verified.")
        )
        return SponsorshipAssessment(
            status=status, claim_type=ClaimType.INFERENCE, confidence=0.35,
            reason=reason, needs_human_verification=True, evidence=list(history),
        )

    return SponsorshipAssessment(
        status=SponsorshipStatus.UNKNOWN, claim_type=ClaimType.UNKNOWN, confidence=0.0,
        reason="No sponsorship statement in the posting and no historical data available.",
        needs_human_verification=True, evidence=[],
    )
