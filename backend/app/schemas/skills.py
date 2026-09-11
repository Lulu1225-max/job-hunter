from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Degree = Literal["Bachelor", "Master", "PhD", "Other"]
EducationField = Literal["university", "degree", "major", "specialisation", "graduation_year"]


class DetectedEducation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university: str | None = None
    degree: Degree | None = None
    major: str | None = None
    specialisation: str | None = None
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)

    @field_validator("university", "major", "specialisation", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        return normalized or None

    @field_validator("degree", mode="before")
    @classmethod
    def normalize_degree(cls, value: str | None) -> Degree | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        if not normalized:
            return None
        lowered = normalized.casefold()
        if any(term in lowered for term in ("bachelor", "本科", "学士")):
            return "Bachelor"
        if any(term in lowered for term in ("master", "硕士", "研究生")):
            return "Master"
        if any(term in lowered for term in ("phd", "ph.d", "doctor of philosophy", "博士")):
            return "PhD"
        if any(term in lowered for term in ("diploma", "associate degree", "certificate", "vocational")) or lowered == "other":
            return "Other"
        return None


class DetectedSkills(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_skills: list[str] = Field(default_factory=list)
    product_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    @field_validator(
        "technical_skills",
        "product_skills",
        "soft_skills",
        "tools",
        "languages",
    )
    @classmethod
    def normalize_items(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = " ".join(value.split()).strip()
            key = item.casefold()
            if item and key not in seen:
                seen.add(key)
                normalized.append(item)
        return normalized


class DetectedResumeInformation(DetectedSkills):
    education: DetectedEducation = Field(default_factory=DetectedEducation)
