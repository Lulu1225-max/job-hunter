from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user, profile_repo
from app.schemas.profile import CareerProfileUpsert

router = APIRouter()


@router.get("")
def get_profile(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    return profile_repo.get(db, user_id) or {}


@router.put("")
def update_profile(payload: CareerProfileUpsert, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    profile = profile_repo.upsert(db, user_id, payload.model_dump())
    db.commit()
    return profile


@router.post("/suggest-skills")
def suggest_skills(payload: dict) -> dict:
    return {
        "technical_skills": ["Docker", "AWS", "Tableau"],
        "soft_skills": ["Stakeholder Management", "Presentation"],
        "requires_confirmation": True,
    }
