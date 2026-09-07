from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class JobBase(BaseModel):
    company: str
    role: str | None = None
    location: str | None = None
    job_url: HttpUrl | str | None = None
    salary: str | None = None
    description: str | None = None
    industry: str | None = None
    job_type: str | None = None
    application_open_date: str | None = None
    deadline: str | None = None
    graduation_cohort: str | None = None
    technical_skills: list[str] = Field(default_factory=list)
    product_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)


class JobCreate(JobBase):
    source: str = "manual"
    external_id: str | None = None


class JobRead(JobCreate):
    id: str
    source_hash: str


class ImportPreviewRequest(BaseModel):
    filepath: str


class ImportConfirmRequest(BaseModel):
    filepath: str
    sheet_name: str


class JobImportRequest(BaseModel):
    filepath: str
    sheet_name: str | None = None
    confirm: bool = False


class ImportCounts(BaseModel):
    total_rows: int
    created: int
    updated: int
    skipped: int
    invalid: int
