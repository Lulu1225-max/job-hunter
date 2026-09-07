from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user, resumes_repo, serialize_model
from app.schemas.resumes import ResumeCreate

router = APIRouter()


@router.get("")
def list_resumes(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> list[dict]:
    ensure_user(db, user_id)
    return resumes_repo.list(db, user_id)


@router.post("")
def create_resume(payload: ResumeCreate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    resume = resumes_repo.create(db, user_id, payload.model_dump())
    db.commit()
    return resume


@router.get("/default")
def get_default_resume(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    resume = resumes_repo.default(db, user_id)
    if not resume:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "No resume found"}})
    return resume


@router.get("/{resume_id}")
def get_resume(resume_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    resume = resumes_repo.get(db, user_id, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    return serialize_model(resume)


@router.put("/{resume_id}")
def update_resume(resume_id: UUID, payload: ResumeCreate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    updated = resumes_repo.update(db, user_id, resume_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    db.commit()
    return updated


@router.patch("/{resume_id}/default")
def set_default_resume(resume_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    updated = resumes_repo.set_default(db, user_id, resume_id)
    if not updated:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    db.commit()
    return updated


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> Response:
    ensure_user(db, user_id)
    deleted = resumes_repo.delete(db, user_id, resume_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    db.commit()
    return Response(status_code=204)
