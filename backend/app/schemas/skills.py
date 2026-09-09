from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DetectedSkills(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_skills: list[str] = Field(default_factory=list)
    product_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    @field_validator("*")
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
