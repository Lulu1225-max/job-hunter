from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.interview_question_bank import InterviewQuestionBankItem
from app.repositories.database import serialize_model
from app.services.analytics import track_event

CATEGORIES = {"Behavioral", "Product", "Technical", "HR", "Other"}


def serialize_item(row: InterviewQuestionBankItem) -> dict:
    return {key: value for key, value in serialize_model(row).items() if key not in {"normalized_question", "seen_keys"}}


def normalize_question(value: str) -> str:
    return " ".join(value.strip().lower().split())


def simple_category(value: str | None) -> str:
    raw = (value or "").casefold()
    if any(term in raw for term in ("technical", "programming", "database", "system design", "coding")): return "Technical"
    if any(term in raw for term in ("product", "metrics", "strategy", "case")): return "Product"
    if any(term in raw for term in ("hr", "motivation", "salary", "culture")): return "HR"
    if any(term in raw for term in ("behavior", "conflict", "leadership", "collaboration")): return "Behavioral"
    return "Other"


class QuestionBankService:
    def list(self, db: Session, user_id: UUID, search: str | None = None,
             category: str | None = None, favorite: bool | None = None) -> list[dict]:
        query = select(InterviewQuestionBankItem).where(InterviewQuestionBankItem.user_id == user_id)
        if search:
            pattern = f"%{normalize_question(search)}%"
            query = query.where(or_(func.lower(InterviewQuestionBankItem.question).like(pattern),
                                    func.lower(func.coalesce(InterviewQuestionBankItem.answer, "")).like(pattern)))
        if category:
            query = query.where(InterviewQuestionBankItem.category == category)
        if favorite is not None:
            query = query.where(InterviewQuestionBankItem.is_favorite == favorite)
        query = query.order_by(InterviewQuestionBankItem.is_favorite.desc(),
                               InterviewQuestionBankItem.times_seen.desc(),
                               InterviewQuestionBankItem.updated_at.desc())
        return [serialize_item(row) for row in db.scalars(query).all()]

    def get(self, db: Session, user_id: UUID, item_id: UUID) -> InterviewQuestionBankItem | None:
        return db.scalar(select(InterviewQuestionBankItem).where(
            InterviewQuestionBankItem.id == item_id, InterviewQuestionBankItem.user_id == user_id))

    def save(self, db: Session, user_id: UUID, *, question: str, answer: str | None = None,
             category: str = "Other", source: str = "manual", replace_answer: bool = False,
             occurrence_key: str | None = None, commit: bool = True, analytics: bool = True) -> dict:
        normalized = normalize_question(question)
        existing = db.scalar(select(InterviewQuestionBankItem).where(
            InterviewQuestionBankItem.user_id == user_id,
            InterviewQuestionBankItem.normalized_question == normalized).with_for_update())
        duplicate = existing is not None
        answer_conflict = False
        incremented = False
        if existing:
            opaque_key = hashlib.sha256(occurrence_key.encode()).hexdigest() if occurrence_key else None
            if not opaque_key or opaque_key not in (existing.seen_keys or []):
                existing.times_seen += 1
                incremented = True
                if opaque_key: existing.seen_keys = [*(existing.seen_keys or []), opaque_key]
            if answer and not existing.answer:
                existing.answer = answer
            elif answer and existing.answer != answer:
                if replace_answer: existing.answer = answer
                else: answer_conflict = True
            row = existing
        else:
            keys = [hashlib.sha256(occurrence_key.encode()).hexdigest()] if occurrence_key else []
            row = InterviewQuestionBankItem(user_id=user_id, question=question.strip(), normalized_question=normalized,
                                            answer=answer or None, category=category, source=source, seen_keys=keys)
            db.add(row)
        db.flush()
        if commit: db.commit()
        if analytics:
            event = "question_bank_item_seen_again" if duplicate and incremented else "question_bank_item_created" if not duplicate else None
            if event: track_event(user_id=user_id, event_name=event, status="success", metadata={"source": source, "category": category})
        return {**serialize_item(row), "duplicate": duplicate, "answer_conflict": answer_conflict,
                "times_seen_incremented": incremented}

    def update(self, db: Session, user_id: UUID, item_id: UUID, payload: dict) -> dict | None:
        row = self.get(db, user_id, item_id)
        if not row: return None
        if payload.get("question"):
            normalized = normalize_question(payload["question"])
            conflict = db.scalar(select(InterviewQuestionBankItem.id).where(
                InterviewQuestionBankItem.user_id == user_id,
                InterviewQuestionBankItem.normalized_question == normalized,
                InterviewQuestionBankItem.id != item_id))
            if conflict: raise ValueError("A Question Bank item with this question already exists")
            row.question, row.normalized_question = payload["question"].strip(), normalized
        for field in ("answer", "category"):
            if field in payload: setattr(row, field, payload[field])
        db.commit()
        track_event(user_id=user_id, event_name="question_bank_item_updated", status="success",
                    metadata={"source": row.source, "category": row.category})
        return serialize_item(row)

    def favorite(self, db: Session, user_id: UUID, item_id: UUID, value: bool) -> dict | None:
        row = self.get(db, user_id, item_id)
        if not row: return None
        row.is_favorite = value; db.commit()
        track_event(user_id=user_id, event_name="question_bank_item_favorited", status="success",
                    metadata={"source": row.source, "category": row.category})
        return serialize_item(row)

    def delete(self, db: Session, user_id: UUID, item_id: UUID) -> bool:
        row = self.get(db, user_id, item_id)
        if not row: return False
        metadata = {"source": row.source, "category": row.category}
        db.delete(row); db.commit()
        track_event(user_id=user_id, event_name="question_bank_item_deleted", status="success", metadata=metadata)
        return True


question_bank_service = QuestionBankService()
