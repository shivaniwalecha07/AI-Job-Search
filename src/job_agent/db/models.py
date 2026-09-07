"""Normalized schema (see ARCHITECTURE.md 5 & 18). Provenance on every derived claim.

Enum-like fields are stored as plain strings validated at the schema/service boundary,
keeping migrations simple and portable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_agent.db.base import Base
from job_agent.db.mixins import ProvenanceMixin, TimestampMixin
from job_agent.db.types import VectorType

EMBED_DIM = 1024  # match your embedding model; voyage-3 = 1024
Vector = VectorType  # portable: pgvector on Postgres, JSON-text fallback elsewhere


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidate"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    needs_sponsorship: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_json: Mapped[dict] = mapped_column(Text)  # serialized verified profile
    resumes: Mapped[list["Resume"]] = relationship(back_populates="candidate")


class Resume(Base, TimestampMixin):
    __tablename__ = "resume"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate.id"))
    version: Mapped[str] = mapped_column(String(80))      # "master" or per-role variant id
    is_master: Mapped[bool] = mapped_column(Boolean, default=False)
    built_for_job_id: Mapped[int | None] = mapped_column(ForeignKey("job.id"), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)   # LaTeX path
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate: Mapped[Candidate] = relationship(back_populates="resumes")


class ResumeChunk(Base):
    """Experience bullets embedded for semantic matching (pgvector)."""
    __tablename__ = "resume_chunk"
    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)


class Company(Base, TimestampMixin):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    name_norm: Mapped[str] = mapped_column(String(300), index=True)
    careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class JobSource(Base, TimestampMixin):
    __tablename__ = "job_source"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(120), unique=True)  # "github:simplify2027"
    source_type: Mapped[str] = mapped_column(String(40))
    requires_supervision: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Job(Base, TimestampMixin):
    __tablename__ = "job"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_job_dedup_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(400), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    ats_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(400))
    title_norm: Mapped[str] = mapped_column(String(400), index=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    location_norm: Mapped[str | None] = mapped_column(String(300), nullable=True)
    remote_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    team: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    posting_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    closing_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ats: Mapped[str | None] = mapped_column(String(40), nullable=True)
    apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(String(120))
    freshness: Mapped[str] = mapped_column(String(10), default="NEW")
    description_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)

    company: Mapped[Company] = relationship(back_populates="jobs")
    sponsorship: Mapped["SponsorshipAssessment"] = relationship(
        back_populates="job", uselist=False
    )
    matches: Mapped[list["JobMatch"]] = relationship(back_populates="job")


class JobEvidence(Base, ProvenanceMixin):
    __tablename__ = "job_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"))
    field: Mapped[str] = mapped_column(String(80))   # which job field this backs


class SponsorshipEvidence(Base, ProvenanceMixin):
    __tablename__ = "sponsorship_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"), nullable=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("job.id"), nullable=True)
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)


class SponsorshipAssessment(Base, TimestampMixin):
    __tablename__ = "sponsorship_assessment"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    claim_type: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    needs_human_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    job: Mapped[Job] = relationship(back_populates="sponsorship")


class JobMatch(Base, TimestampMixin):
    __tablename__ = "job_match"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate.id"))
    overall: Mapped[int] = mapped_column(Integer)
    technical: Mapped[int] = mapped_column(Integer)
    experience: Mapped[int] = mapped_column(Integer)
    education: Mapped[int] = mapped_column(Integer)
    domain: Mapped[int] = mapped_column(Integer)
    location: Mapped[int] = mapped_column(Integer)
    authorization: Mapped[int] = mapped_column(Integer)
    seniority: Mapped[int] = mapped_column(Integer)
    strengths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    gaps_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_opportunities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_components_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    job: Mapped[Job] = relationship(back_populates="matches")


class Application(Base, TimestampMixin):
    __tablename__ = "application"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate.id"))
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resume.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="DISCOVERED")
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    referral: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answers: Mapped[list["ApplicationAnswer"]] = relationship(back_populates="application")
    events: Mapped[list["ApplicationEvent"]] = relationship(back_populates="application")


class ApplicationAnswer(Base):
    __tablename__ = "application_answer"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    question: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(20))  # AUTO_ANSWERABLE|NEEDS_REVIEW|MUST_ASK_USER
    draft_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    application: Mapped[Application] = relationship(back_populates="answers")


class ApplicationEvent(Base):
    """Append-only audit log of every state change and automated action (observability + audit)."""
    __tablename__ = "application_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    at: Mapped[datetime] = mapped_column(DateTime)
    actor: Mapped[str] = mapped_column(String(40))  # "agent" | "human"
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    application: Mapped[Application] = relationship(back_populates="events")


# ---- Networking (deferred; schema present so no reshape later) ----
class Recruiter(Base, TimestampMixin):
    __tablename__ = "recruiter"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)


class NetworkingContact(Base, TimestampMixin):
    __tablename__ = "networking_contact"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConnectionRequest(Base, TimestampMixin):
    __tablename__ = "connection_request"
    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("networking_contact.id"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFTED")  # never auto-sent
    draft_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Message(Base, TimestampMixin):
    __tablename__ = "message"
    id: Mapped[int] = mapped_column(primary_key=True)
    connection_request_id: Mapped[int] = mapped_column(ForeignKey("connection_request.id"))
    kind: Mapped[str] = mapped_column(String(20))  # follow_up, etc.
    status: Mapped[str] = mapped_column(String(20), default="DRAFTED")
    body: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---- Observability ----
class PipelineRun(Base):
    __tablename__ = "pipeline_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    supervised: Mapped[bool] = mapped_column(Boolean, default=False)
    counts_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # per-stage counts
    status: Mapped[str] = mapped_column(String(20), default="running")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
