from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class MatchEvidence(BaseModel):
    skill: str
    snippet: str = Field(max_length=320)


class RewriteSuggestion(BaseModel):
    type: str
    text: str


class MatchNarrative(BaseModel):
    explanation: str
    evidence: list[MatchEvidence] = Field(default_factory=list, max_length=8)
    weak_areas: list[str] = Field(default_factory=list, max_length=8)
    rewrite_suggestions: list[RewriteSuggestion] = Field(default_factory=list, max_length=8)


class DiscoveryMatch(BaseModel):
    status: Literal["ready", "scored", "semantic_only", "limited_data", "no_resume"]
    overall_score: int | None = None
    semantic_score: int | None = None
    components: dict[str, int | None] = Field(default_factory=dict)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    missing_jd: bool = False
    explanation: str
    cached: bool = False


class ResumeMatchResult(BaseModel):
    analysis_id: str
    job_id: str
    resume_id: str
    status: Literal["scored", "semantic_only"]
    overall_score: int | None
    keyword_score: int | None
    semantic_score: int
    experience_relevance_score: int | None
    matched_keywords: list[str]
    missing_keywords: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    evidence: list[MatchEvidence]
    weak_areas: list[str]
    explanation: str
    suggested_resume_improvements: list[RewriteSuggestion]
    cached: bool
    analysis_version: str
