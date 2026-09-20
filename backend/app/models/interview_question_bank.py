from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class InterviewQuestionBankItem(TimestampMixin, Base):
    __tablename__ = "interview_question_bank"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_question", name="uq_question_bank_user_normalized"),
        Index("ix_question_bank_user_sort", "user_id", "is_favorite", "times_seen", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="Other", index=True)
    times_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    # Opaque request hashes make Actual Interview retries idempotent; no question text is stored here.
    seen_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
