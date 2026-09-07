from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Application(TimestampMixin, Base):
    __tablename__ = "applications"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"))
    company: Mapped[str] = mapped_column(String(250), nullable=False)
    role: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(Text)
    job_url: Mapped[str | None] = mapped_column(Text)
    salary: Mapped[str | None] = mapped_column(String(250))
    application_date: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="saved", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
