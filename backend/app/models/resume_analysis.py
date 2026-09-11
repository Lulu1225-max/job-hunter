from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ResumeAnalysis(TimestampMixin, Base):
    __tablename__ = "resume_analyses"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    keyword_score: Mapped[int | None] = mapped_column(Integer)
    semantic_score: Mapped[int] = mapped_column(Integer, nullable=False)
    experience_score: Mapped[int | None] = mapped_column(Integer)
    overall_score: Mapped[int | None] = mapped_column(Integer)
    matched_keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    missing_keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    matched_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    suggestions: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    evidence: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    weak_areas: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    resume_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    job_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False, default="phase5-v1")
    response_language: Mapped[str] = mapped_column(String(20), nullable=False, default="chinese")
