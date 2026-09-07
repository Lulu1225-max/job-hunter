from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    round: Mapped[int | None] = mapped_column(Integer)
    interview_type: Mapped[str | None] = mapped_column(String(80))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default="scheduled", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
