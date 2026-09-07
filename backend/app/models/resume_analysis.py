from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer
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
    keyword_score: Mapped[int] = mapped_column(Integer, nullable=False)
    semantic_score: Mapped[int] = mapped_column(Integer, nullable=False)
    experience_score: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    missing_keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    matched_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    suggestions: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
