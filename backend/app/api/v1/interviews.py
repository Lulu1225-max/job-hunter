from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import (
    ensure_user,
    experiences_repo,
    interview_answers_repo,
    interview_questions_repo,
    interviews_repo,
    serialize_model,
)
from app.services.matching import analyse_user_answer, generate_answer, retrieve_experiences

router = APIRouter()


@router.get("/interviews")
def list_interviews(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> list[dict]:
    ensure_user(db, user_id)
    return interviews_repo.list(db, user_id)


@router.post("/applications/{application_id}/interview-prep")
def prepare_interview(application_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    interview = interviews_repo.get_by_application(db, user_id, application_id)
    if not interview:
        return {"application_id": str(application_id), "questions": [], "likely_topics": [], "recommended_experiences": []}
    application = interview["application"]
    questions = interview_questions_repo.list_for_application(db, user_id, application_id)
    experiences = experiences_repo.list(db, user_id)
    target = {"company": application["company"], "role": application["role"], "questions": questions}
    return {
        "interview": interview,
        "application": application,
        "likely_topics": [
            "Product Thinking",
            "AI Product Understanding",
            "User Growth / Retention",
            "Product Metrics",
            "Product Case Analysis",
            "Cross-functional Collaboration",
            "Stakeholder Management",
            "Behavioural Reflection",
            "Company Motivation",
            "Career Motivation",
        ],
        "public_research_questions": [q for q in questions if q["source"] == "public_research"],
        "ai_generated_questions": [q for q in questions if q["source"] == "ai_generated"],
        "user_added_questions": [q for q in questions if q["source"] == "user_added"],
        "recommended_experiences": retrieve_experiences(target, experiences)[:4],
    }


@router.post("/interview/questions")
def add_question(payload: dict, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    question = interview_questions_repo.create(db, user_id, payload)
    db.commit()
    return question


@router.get("/interview/questions/{question_id}/experiences")
def question_experiences(question_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    question = interview_questions_repo.get(db, user_id, question_id)
    if not question:
        raise HTTPException(status_code=404, detail={"error": {"code": "QUESTION_NOT_FOUND", "message": "Question not found"}})
    experiences = experiences_repo.list(db, user_id)
    return {"question": serialize_model(question), "recommended_experiences": retrieve_experiences(serialize_model(question), experiences)[:4]}


@router.post("/interview/questions/{question_id}/answers")
def create_answer(question_id: UUID, payload: dict, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    question = interview_questions_repo.get(db, user_id, question_id)
    if not question:
        raise HTTPException(status_code=404, detail={"error": {"code": "QUESTION_NOT_FOUND", "message": "Question not found"}})
    experience_id = payload.get("experience_id")
    experience = experiences_repo.get(db, user_id, UUID(experience_id)) if experience_id else None
    if not experience:
        raise HTTPException(status_code=404, detail={"error": {"code": "EXPERIENCE_NOT_FOUND", "message": "Experience not found"}})
    generated = generate_answer(serialize_model(question), serialize_model(experience))
    answer = interview_answers_repo.create(db, {"question_id": question_id, "experience_id": experience.id, **generated})
    db.commit()
    return answer


@router.post("/interview/questions/{question_id}/analyse-answer")
def analyse_answer(question_id: UUID, payload: dict, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    question = interview_questions_repo.get(db, user_id, question_id)
    if not question:
        raise HTTPException(status_code=404, detail={"error": {"code": "QUESTION_NOT_FOUND", "message": "Question not found"}})
    return analyse_user_answer(str(payload.get("answer", "")), serialize_model(question), experiences_repo.list(db, user_id))


@router.post("/interview/questions/import")
def import_questions(payload: dict) -> dict:
    raw = str(payload.get("text", ""))
    parsed = [{"question": line.strip(" -\t"), "source": "user_added"} for line in raw.splitlines() if line.strip("?？ ")]
    return {"questions": parsed, "requires_confirmation": True}
