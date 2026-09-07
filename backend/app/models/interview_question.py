from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class InterviewQuestion(TimestampMixin, Base):
    __tablename__ = "interview_questions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    interview_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("interviews.id", ondelete="SET NULL"))
    application_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"))
    company: Mapped[str | None] = mapped_column(String(250))
    role: Mapped[str | None] = mapped_column(String(300))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="other", nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="user_added", nullable=False)
    source_platform: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int | None] = mapped_column(Integer)
    user_answer: Mapped[str | None] = mapped_column(Text)
    ai_feedback: Mapped[dict | None] = mapped_column(JSONB)
