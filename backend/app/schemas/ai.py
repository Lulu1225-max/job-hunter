from __future__ import annotations

from pydantic import BaseModel, Field


class ParsedApplicationEmail(BaseModel):
    company: str | None = None
    role: str | None = None
    status: str | None = None
    interview_date: str | None = None
    deadline: str | None = None
    location: str | None = None
    confidence: float = Field(ge=0, le=1, default=0)


class ApplicationEmailParseRequest(BaseModel):
    text: str
