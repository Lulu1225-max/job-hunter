from __future__ import annotations

import hashlib
from typing import Any
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.ai.client import ai_client


def _normalized(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return " ".join(str(value).replace("\x00", "").split())


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resume_source(resume: Any) -> str:
    return _normalized(resume.extracted_text)


def job_source(job: Any) -> str:
    fields = [
        ("Description", job.description), ("Description context", job.description),
        ("Role", job.role), ("Company", job.company), ("Location", job.location),
        ("Industry", job.industry), ("Job type", job.job_type),
        ("Campus category", job.campus_category), ("Graduation cohort", job.graduation_cohort),
        ("Company type", job.company_type), ("Required skills", job.required_skills),
        ("Technical skills", job.technical_skills), ("Product skills", job.product_skills),
    ]
    return "\n".join(f"{label}: {_normalized(value)}" for label, value in fields if _normalized(value))


def experience_source(experience: Any) -> str:
    fields = [
        ("Title", experience.title), ("Type", experience.type),
        ("Description", experience.description), ("Situation", experience.situation),
        ("Task", experience.task), ("Action", experience.action),
        ("Result", experience.result), ("Reflection", experience.reflection),
        ("Skills", experience.skills), ("Technologies", experience.technologies),
    ]
    return "\n".join(f"{label}: {_normalized(value)}" for label, value in fields if _normalized(value))


class EmbeddingService:
    def ensure_experience(self, db: Session, experience: Any) -> tuple[list[float], str]:
        source = experience_source(experience)
        digest = fingerprint(source)
        if experience.embedding is not None and experience.embedding_fingerprint == digest:
            return list(experience.embedding), digest
        experience.embedding = ai_client.get_embedding(source[: settings.embedding_max_characters])
        experience.embedding_fingerprint = digest
        db.flush()
        return list(experience.embedding), digest
    def ensure_resume(self, db: Session, resume: Any) -> tuple[list[float], str]:
        source = resume_source(resume)
        if not source:
            raise ValueError("Resume has no extracted text")
        digest = fingerprint(source)
        if resume.embedding is not None and resume.embedding_fingerprint == digest:
            return list(resume.embedding), digest
        resume.embedding = ai_client.get_embedding(source[: settings.embedding_max_characters])
        resume.embedding_fingerprint = digest
        db.flush()
        return list(resume.embedding), digest

    def ensure_job(self, db: Session, job: Any) -> tuple[list[float], str]:
        source = job_source(job)
        digest = fingerprint(source)
        if job.embedding is not None and job.embedding_fingerprint == digest:
            return list(job.embedding), digest
        job.embedding = ai_client.get_embedding(source[: settings.embedding_max_characters])
        job.embedding_fingerprint = digest
        db.flush()
        return list(job.embedding), digest


embedding_service = EmbeddingService()
