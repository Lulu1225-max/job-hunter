from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.database import experiences_repo, profile_repo, serialize_model
from app.schemas.experiences import ExperienceOrganization
from app.services.ai.client import ai_client
from app.services.embedding_service import embedding_service, experience_source, fingerprint
from app.services.matching import response_language, tokens

RETRIEVAL_CANDIDATE_LIMIT = 5
DEFAULT_RECOMMENDATION_LIMIT = 3
MAX_LAZY_EMBEDS_PER_RETRIEVAL = 5
RETRIEVAL_WEIGHTS = {"semantic": .80, "skills": .10, "type": .05, "completeness": .05}
TYPE_TERMS = {
    "internship": ("internship", "intern", "实习"), "project": ("project", "项目"),
    "coursework": ("coursework", "course", "课程"), "leadership": ("leadership", "leader", "领导"),
    "volunteer": ("volunteer", "志愿"), "competition": ("competition", "竞赛", "比赛"), "other": ("other", "其他"),
}


class ExperienceService:
    def list(self, db: Session, user_id: UUID) -> list[dict[str, Any]]:
        return experiences_repo.list(db, user_id)

    def get(self, db: Session, user_id: UUID, experience_id: UUID):
        return experiences_repo.get(db, user_id, experience_id)

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        row = experiences_repo.create(db, user_id, payload)
        self._best_effort_embedding(db, row)
        db.commit()
        return serialize_model(row)

    def update(self, db: Session, user_id: UUID, experience_id: UUID, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = experiences_repo.get(db, user_id, experience_id)
        if not row:
            return None
        before = fingerprint(experience_source(row))
        row = experiences_repo.update(db, user_id, experience_id, payload)
        if not any(str(getattr(row, key) or "").strip() for key in ("description", "situation", "task", "action", "result")):
            raise ValueError("Description or meaningful structured experience content is required")
        if fingerprint(experience_source(row)) != before:
            row.embedding = None
            row.embedding_fingerprint = None
            self._best_effort_embedding(db, row)
        db.commit()
        return serialize_model(row)

    def delete(self, db: Session, user_id: UUID, experience_id: UUID) -> bool:
        deleted = experiences_repo.delete(db, user_id, experience_id)
        if deleted:
            db.commit()
        return deleted

    def organize(self, db: Session, user_id: UUID, rough_notes: str) -> dict[str, Any]:
        language = response_language(profile_repo.get(db, user_id))
        proposal = ai_client.structured_completion(
            prompt_name="experience_organizer",
            schema=ExperienceOrganization,
            payload={"response_language": language, "rough_notes": rough_notes},
        )
        source_numbers = set(re.findall(r"\d+(?:[.,]\d+)?%?", rough_notes))
        values = proposal.proposal.model_dump()
        for field in ("title", "description", "situation", "task", "action", "result", "reflection"):
            value = values.get(field)
            if value and not set(re.findall(r"\d+(?:[.,]\d+)?%?", value)).issubset(source_numbers):
                values[field] = None
        lower_notes = rough_notes.casefold()
        values["technologies"] = [item for item in values["technologies"] if item.casefold() in lower_notes]
        return {"proposal": values, "follow_up_questions": proposal.follow_up_questions, "response_language": language, "saved": False}

    def retrieve(self, db: Session, user_id: UUID, query: str, job_context: str | None, limit: int, job_id: UUID | None = None) -> dict[str, Any]:
        from time import perf_counter
        from app.services.analytics import elapsed_ms, track_event
        started = perf_counter()
        query_text = query.strip() + (f"\nJob context: {job_context.strip()}" if job_context and job_context.strip() else "")
        query_vector = ai_client.get_embedding(query_text)
        embedded = 0
        for row in experiences_repo.missing_embeddings(db, user_id, MAX_LAZY_EMBEDS_PER_RETRIEVAL):
            if self._best_effort_embedding(db, row):
                embedded += 1
        if embedded:
            db.commit()
        candidates = experiences_repo.vector_search(db, user_id, query_vector, RETRIEVAL_CANDIDATE_LIMIT)
        language = response_language(profile_repo.get(db, user_id))
        ranked_items = []
        query_tokens = tokens(query)
        query_lower = query.casefold()
        for row, distance in candidates:
            similarity = max(-1.0, min(1.0, 1.0 - distance))
            relevant = [item for item in [*(row.skills or []), *(row.technologies or [])] if tokens(item) & query_tokens]
            skills_score = min(1.0, len(relevant) / 2)
            type_score = 1.0 if any(term in query_lower for term in TYPE_TERMS.get(row.type, ())) else None
            completeness = sum(bool(str(getattr(row, key) or "").strip()) for key in ("description", "situation", "task", "action", "result", "reflection")) / 6
            components = {"semantic": max(0.0, similarity), "skills": skills_score, "type": type_score, "completeness": completeness}
            available = [(components[key], weight) for key, weight in RETRIEVAL_WEIGHTS.items() if components[key] is not None]
            rank_score = sum(value * weight for value, weight in available) / sum(weight for _, weight in available)
            level = "high" if similarity >= .65 else "medium" if similarity >= .4 else "lower"
            ranked_items.append((rank_score, {
                "experience_id": str(row.id), "title": row.title, "type": row.type,
                "similarity": round(similarity, 4), "relevance": level,
                "reason": self._reason(language, row, relevant),
                "skills": (row.skills or [])[:5], "technologies": (row.technologies or [])[:5],
                "selected": False,
            }))
        items = [item for _, item in sorted(ranked_items, key=lambda value: value[0], reverse=True)[:limit]]
        track_event(user_id=user_id, event_name="experience_retrieved", job_id=job_id, status="success",
                    latency_ms=elapsed_ms(started), metadata={"candidate_count": len(candidates), "returned_count": len(items)})
        return {"query": query, "recommendations": items, "selected_experience_id": None, "embedded_missing_count": embedded}

    def _best_effort_embedding(self, db: Session, row: Any) -> bool:
        try:
            embedding_service.ensure_experience(db, row)
            return True
        except Exception:
            row.embedding = None
            row.embedding_fingerprint = None
            return False

    @staticmethod
    def _reason(language: str, row: Any, relevant: list[str]) -> str:
        evidence = ", ".join(relevant[:3]) or row.title
        if language == "english":
            return f"Relevant themes from this saved experience: {evidence}."
        if language == "bilingual":
            return f"该经历包含相关主题：{evidence}。 / Relevant saved themes: {evidence}."
        return f"该经历包含相关主题：{evidence}。"


experience_service = ExperienceService()
