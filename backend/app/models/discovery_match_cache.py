from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class DiscoveryMatchCache(TimestampMixin, Base):
    __tablename__ = "discovery_match_caches"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "resume_id", "job_id", "resume_fingerprint", "job_fingerprint", "scoring_version",
            name="uq_discovery_match_cache_source_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    job_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
