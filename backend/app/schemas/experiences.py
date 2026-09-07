from __future__ import annotations

from pydantic import BaseModel, Field


class ExperienceCreate(BaseModel):
    title: str
    type: str
    description: str | None = None
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ExperienceUpdate(BaseModel):
    title: str | None = None
    type: str | None = None
    description: str | None = None
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    skills: list[str] | None = None
    technologies: list[str] | None = None
