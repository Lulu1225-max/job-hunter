from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class InterviewAnswer(TimestampMixin, Base):
    __tablename__ = "interview_answers"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False)
    experience_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("experiences.id", ondelete="SET NULL"))
    answer_30s: Mapped[str | None] = mapped_column(Text)
    answer_1min: Mapped[str | None] = mapped_column(Text)
    answer_2min: Mapped[str | None] = mapped_column(Text)
    response_language: Mapped[str] = mapped_column(String(20), nullable=False)
    feedback: Mapped[dict | None] = mapped_column(JSONB)
    follow_up_questions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    question_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    experience_fingerprint: Mapped[str | None] = mapped_column(String(64))
    job_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    answer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
