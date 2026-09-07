"""Typed contracts between agents. Agents depend on these, not on each other."""
from job_agent.schemas.core import (
    ApplicationPackage,
    ClaimType,
    JobMatch,
    NormalizedJob,
    RankedJob,
    RawJobRecord,
    SourceHealth,
    SponsorshipAssessment,
    SponsorshipEvidence,
    SponsorshipStatus,
)

__all__ = [
    "ApplicationPackage",
    "ClaimType",
    "JobMatch",
    "NormalizedJob",
    "RankedJob",
    "RawJobRecord",
    "SourceHealth",
    "SponsorshipAssessment",
    "SponsorshipEvidence",
    "SponsorshipStatus",
]
