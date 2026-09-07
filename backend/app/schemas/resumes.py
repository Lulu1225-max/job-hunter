from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeCreate(BaseModel):
    name: str
    file_url: str
    extracted_text: str | None = None
    structured_content: dict = Field(default_factory=dict)
    is_default: bool | None = None


class ResumeRead(ResumeCreate):
    id: str
    is_default: bool
