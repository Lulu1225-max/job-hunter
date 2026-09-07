from __future__ import annotations

from pydantic import BaseModel, Field


class CareerProfileUpsert(BaseModel):
    display_name: str | None = None
    target_roles: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    target_industries: list[str] = Field(default_factory=list)
    preferred_job_types: list[str] = Field(default_factory=list)
    university: str | None = None
    degree: str | None = None
    major: str | None = None
    specialisation: str | None = None
    graduation_year: int | None = None
    technical_skills: list[str] = Field(default_factory=list)
    product_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    ai_response_language: str = "chinese"
