from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class CareerProfile(TimestampMixin, Base):
    __tablename__ = "career_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_career_profiles_user_id"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    target_roles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    target_locations: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    target_industries: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    preferred_job_types: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    university: Mapped[str | None] = mapped_column(String(250))
    degree: Mapped[str | None] = mapped_column(String(250))
    major: Mapped[str | None] = mapped_column(String(250))
    specialisation: Mapped[str | None] = mapped_column(String(250))
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    technical_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    product_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    soft_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    tools: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    languages: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    ai_response_language: Mapped[str] = mapped_column(String(20), default="bilingual", nullable=False)
