from __future__ import annotations

from pydantic import BaseModel


class ApplicationCreate(BaseModel):
    job_id: str | None = None
    company: str
    role: str | None = None
    location: str | None = None
    job_url: str | None = None
    salary: str | None = None
    application_date: str | None = None
    deadline: str | None = None
    status: str = "saved"
    notes: str | None = None
    source: str = "manual"


class ApplicationUpdate(BaseModel):
    job_id: str | None = None
    company: str | None = None
    role: str | None = None
    location: str | None = None
    job_url: str | None = None
    salary: str | None = None
    application_date: str | None = None
    deadline: str | None = None
    status: str | None = None
    notes: str | None = None
    source: str | None = None


class ApplicationRead(ApplicationCreate):
    id: str
