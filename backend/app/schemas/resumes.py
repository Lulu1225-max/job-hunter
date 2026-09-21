from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.skills import DetectedResumeInformation, DetectedSkills, EducationField


class ResumeCreate(BaseModel):
    name: str
    file_url: str
    file_type: str
    extracted_text: str | None = None
    structured_content: dict = Field(default_factory=dict)
    detected_skills: DetectedResumeInformation = Field(default_factory=DetectedResumeInformation)
    is_default: bool | None = None


class ResumeRead(ResumeCreate):
    id: str
    user_id: str
    is_default: bool
    created_at: str
    updated_at: str


class ResumeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    is_default: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Resume name cannot be empty")
        return value


class ConfirmResumeSkills(BaseModel):
    skills: DetectedSkills
    education_fields: list[EducationField] = Field(default_factory=list)
