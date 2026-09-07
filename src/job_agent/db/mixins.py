"""Reusable column mixins: timestamps and the provenance/confidence pattern.

Any table holding a *derived* claim mixes in ProvenanceMixin so FACT/INFERENCE/UNKNOWN,
confidence, source, and evidence travel with the claim (see ARCHITECTURE.md 5).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ProvenanceMixin:
    claim_type: Mapped[str] = mapped_column(String(16), default="UNKNOWN")   # FACT|INFERENCE|UNKNOWN
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
