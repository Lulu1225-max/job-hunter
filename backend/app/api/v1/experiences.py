from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user, serialize_model
from app.schemas.experiences import ExperienceCreate, ExperienceUpdate, OrganizeExperienceRequest, RetrieveExperiencesRequest
from app.services.experience_service import experience_service

router = APIRouter()


@router.get("")
def list_experiences(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> list[dict]:
    ensure_user(db, user_id)
    return experience_service.list(db, user_id)


@router.post("")
def create_experience(payload: ExperienceCreate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    return experience_service.create(db, user_id, payload.model_dump())


@router.post("/organize")
def organize_experience(payload: OrganizeExperienceRequest, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    try:
        return experience_service.organize(db, user_id, payload.rough_notes)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error": {"code": "AI_ORGANIZATION_UNAVAILABLE", "message": "Experience organization is temporarily unavailable"}}) from exc


@router.post("/retrieve")
def retrieve_experiences(payload: RetrieveExperiencesRequest, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    try:
        return experience_service.retrieve(db, user_id, payload.query, payload.job_context, payload.limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error": {"code": "EXPERIENCE_RETRIEVAL_UNAVAILABLE", "message": "Experience retrieval is temporarily unavailable"}}) from exc


@router.get("/{experience_id}")
def get_experience(experience_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    experience = experience_service.get(db, user_id, experience_id)
    if not experience:
        raise HTTPException(status_code=404, detail={"error": {"code": "EXPERIENCE_NOT_FOUND", "message": "Experience not found"}})
    return serialize_model(experience)


def _update(experience_id: UUID, payload: ExperienceUpdate, db: Session, user_id: UUID) -> dict:
    ensure_user(db, user_id)
    try:
        updated = experience_service.update(db, user_id, experience_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": {"code": "INVALID_EXPERIENCE", "message": str(exc)}}) from exc
    if not updated:
        raise HTTPException(status_code=404, detail={"error": {"code": "EXPERIENCE_NOT_FOUND", "message": "Experience not found"}})
    return updated


@router.put("/{experience_id}")
def update_experience(experience_id: UUID, payload: ExperienceUpdate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    return _update(experience_id, payload, db, user_id)


@router.patch("/{experience_id}")
def patch_experience(experience_id: UUID, payload: ExperienceUpdate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    return _update(experience_id, payload, db, user_id)


@router.delete("/{experience_id}", status_code=204)
def delete_experience(experience_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> Response:
    ensure_user(db, user_id)
    if not experience_service.delete(db, user_id, experience_id):
        raise HTTPException(status_code=404, detail={"error": {"code": "EXPERIENCE_NOT_FOUND", "message": "Experience not found"}})
    return Response(status_code=204)
