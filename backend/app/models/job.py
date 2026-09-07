from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("user_id", "source_hash", name="uq_jobs_user_source_hash"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(250))
    company: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(300), index=True)
    location: Mapped[str | None] = mapped_column(Text, index=True)
    job_url: Mapped[str | None] = mapped_column(Text)
    salary: Mapped[str | None] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(250), index=True)
    job_type: Mapped[str | None] = mapped_column(String(80), index=True)
    application_open_date: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date, index=True)
    graduation_cohort: Mapped[str | None] = mapped_column(String(120), index=True)
    technical_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    product_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    soft_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    required_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    education_requirements: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
