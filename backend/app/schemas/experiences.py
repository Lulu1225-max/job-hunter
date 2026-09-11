from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator

ExperienceType = Literal["internship", "project", "coursework", "leadership", "volunteer", "competition", "other"]


class ExperienceFields(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    type: ExperienceType
    description: str | None = None
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    reflection: str | None = None
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_narrative(self):
        if not any(str(getattr(self, key) or "").strip() for key in ("description", "situation", "task", "action", "result")):
            raise ValueError("Description or meaningful structured experience content is required")
        return self


class ExperienceCreate(ExperienceFields):
    pass


class ExperienceUpdate(BaseModel):
    title: str | None = None
    type: ExperienceType | None = None
    description: str | None = None
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    reflection: str | None = None
    skills: list[str] | None = None
    technologies: list[str] | None = None


class ExperienceProposal(BaseModel):
    title: str | None = None
    type: ExperienceType | None = None
    description: str | None = None
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    reflection: str | None = None
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ExperienceOrganization(BaseModel):
    proposal: ExperienceProposal
    follow_up_questions: list[str] = Field(default_factory=list, max_length=4)


class OrganizeExperienceRequest(BaseModel):
    rough_notes: str = Field(min_length=10, max_length=12000)


class RetrieveExperiencesRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    job_context: str | None = Field(default=None, max_length=4000)
    limit: int = Field(default=3, ge=1, le=5)
