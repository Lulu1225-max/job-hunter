from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (Index("ix_analytics_events_user_created", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    job_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"))
    resume_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"))
    experience_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("experiences.id", ondelete="SET NULL"))
    status: Mapped[str | None] = mapped_column(String(16))
    error_type: Mapped[str | None] = mapped_column(String(80))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
