from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
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
