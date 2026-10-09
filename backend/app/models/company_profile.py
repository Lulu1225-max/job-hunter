from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class CompanyProfile(TimestampMixin, Base):
    __tablename__ = "company_profiles"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_name: Mapped[str] = mapped_column(String(250), nullable=False)
    normalized_company_name: Mapped[str] = mapped_column(String(250), nullable=False, unique=True, index=True)
    positioning: Mapped[str] = mapped_column(Text, nullable=False)
    business_lines: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    key_brands: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    key_products: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    customer_groups: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    strategic_focus: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    comparable_products: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    interview_notes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    generation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
