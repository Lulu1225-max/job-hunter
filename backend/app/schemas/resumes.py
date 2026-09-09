from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.skills import DetectedSkills


class ResumeCreate(BaseModel):
    name: str
    file_url: str
    file_type: str
    extracted_text: str | None = None
    structured_content: dict = Field(default_factory=dict)
    detected_skills: DetectedSkills = Field(default_factory=DetectedSkills)
    is_default: bool | None = None


class ResumeRead(ResumeCreate):
    id: str
    user_id: str
    is_default: bool
    created_at: str
    updated_at: str


class ResumeUpdate(BaseModel):
    name: str | None = None
    is_default: bool | None = None


class ConfirmResumeSkills(BaseModel):
    skills: DetectedSkills
