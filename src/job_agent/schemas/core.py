"""Core agent I/O contracts (see ARCHITECTURE.md 7).

Every derived claim carries provenance + a FACT/INFERENCE/UNKNOWN label. These models
are the boundary types; the DB models in db/models.py persist them.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- enums
class ClaimType(str, Enum):
    FACT = "FACT"          # directly supported by a source
    INFERENCE = "INFERENCE"  # reasonable conclusion from evidence
    UNKNOWN = "UNKNOWN"    # insufficient evidence


class SponsorshipStatus(str, Enum):
    YES = "YES"
    NO = "NO"
    UNCLEAR = "UNCLEAR"
    JOB_SPECIFIC = "JOB_SPECIFIC"
    COMPANY_SPECIFIC = "COMPANY_SPECIFIC"
    UNKNOWN = "UNKNOWN"


class Freshness(str, Enum):
    NEW = "NEW"
    RECENT = "RECENT"
    STALE = "STALE"


SourceType = Literal[
    "job_description",
    "uscis_datahub",
    "dol_oflc",
    "career_page",
    "github_list",
    "ats_api",
    "linkedin",
    "llm_inference",
]


# ----------------------------------------------------------------- discovery layer
class SourceHealth(BaseModel):
    source_id: str
    ok: bool
    detail: str = ""
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class RawJobRecord(BaseModel):
    """Raw payload from a connector. Connectors pull; they do NOT normalize."""
    source_id: str
    source_type: SourceType
    raw_url: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any]


class NormalizedJob(BaseModel):
    dedup_key: str
    title: str
    title_norm: str
    company: str
    company_norm: str
    location: Optional[str] = None
    location_norm: Optional[str] = None
    remote_mode: Optional[str] = None          # remote | hybrid | onsite
    employment_type: Optional[str] = None       # internship | full_time
    team: Optional[str] = None
    description: Optional[str] = None
    required_qualifications: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    compensation: Optional[str] = None
    posting_date: Optional[datetime] = None
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    closing_date: Optional[datetime] = None
    ats: Optional[str] = None
    apply_url: Optional[str] = None
    source_url: str
    source_id: str
    freshness: Freshness = Freshness.NEW


# ---------------------------------------------------------------- sponsorship
class SponsorshipEvidence(BaseModel):
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: SourceType
    source_url: str
    evidence_text: Optional[str] = None        # verbatim supporting quote
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    is_historical: bool = False                 # e.g. past H-1B, full-time only


class SponsorshipAssessment(BaseModel):
    status: SponsorshipStatus
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    needs_human_verification: bool = False
    evidence: list[SponsorshipEvidence] = Field(default_factory=list)


# ---------------------------------------------------------------- matching
class JobMatch(BaseModel):
    overall: int = Field(ge=0, le=100)
    technical: int = Field(ge=0, le=100)
    experience: int = Field(ge=0, le=100)
    education: int = Field(ge=0, le=100)
    domain: int = Field(ge=0, le=100)
    location: int = Field(ge=0, le=100)
    authorization: int = Field(ge=0, le=100)
    seniority: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    resume_opportunities: list[str] = Field(default_factory=list)  # emphasize existing bullets only


# ---------------------------------------------------------------- ranking
class RankedJob(BaseModel):
    job_id: str
    final_score: float
    components: dict[str, float] = Field(default_factory=dict)  # weighted contributions
    rationale: str = ""


# ---------------------------------------------------------------- application
class QuestionClass(str, Enum):
    AUTO_ANSWERABLE = "AUTO_ANSWERABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MUST_ASK_USER = "MUST_ASK_USER"


class ClassifiedAnswer(BaseModel):
    question: str
    classification: QuestionClass
    draft_answer: Optional[str] = None
    source_note: Optional[str] = None          # which profile fact backs the answer


class ApplicationPackage(BaseModel):
    job_id: str
    resume_version: str
    cover_letter: Optional[str] = None
    answers: list[ClassifiedAnswer] = Field(default_factory=list)
    questions_requiring_user: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
