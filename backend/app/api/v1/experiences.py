from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user, experiences_repo, serialize_model
from app.schemas.experiences import ExperienceCreate, ExperienceUpdate

router = APIRouter()


@router.get("")
def list_experiences(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> list[dict]:
    ensure_user(db, user_id)
    return experiences_repo.list(db, user_id)


@router.post("")
def create_experience(payload: ExperienceCreate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    experience = experiences_repo.create(db, user_id, payload.model_dump())
    db.commit()
    return experience


@router.get("/{experience_id}")
def get_experience(experience_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    experience = experiences_repo.get(db, user_id, experience_id)
    if not experience:
        raise HTTPException(status_code=404, detail={"error": {"code": "EXPERIENCE_NOT_FOUND", "message": "Experience not found"}})
    return serialize_model(experience)


@router.put("/{experience_id}")
def update_experience(
    experience_id: UUID,
    payload: ExperienceUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    ensure_user(db, user_id)
    updated = experiences_repo.update(db, user_id, experience_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail={"error": {"code": "EXPERIENCE_NOT_FOUND", "message": "Experience not found"}})
    db.commit()
    return updated


@router.delete("/{experience_id}", status_code=204)
def delete_experience(experience_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> Response:
    ensure_user(db, user_id)
    deleted = experiences_repo.delete(db, user_id, experience_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": {"code": "EXPERIENCE_NOT_FOUND", "message": "Experience not found"}})
    db.commit()
    return Response(status_code=204)


@router.post("/search")
def search_experiences(payload: dict, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> list[dict]:
    ensure_user(db, user_id)
    return experiences_repo.search(db, user_id, str(payload.get("query", "")))
