from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user, resumes_repo, serialize_model
from app.schemas.resumes import ConfirmResumeSkills, ResumeUpdate
from app.services.resume_service import ResumeUploadError, resume_service
from app.services.storage import StorageError, resume_storage

router = APIRouter()


@router.get("")
def list_resumes(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> list[dict]:
    ensure_user(db, user_id)
    return resumes_repo.list(db, user_id)


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    is_default: bool | None = Form(default=None),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    ensure_user(db, user_id)
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > settings.resume_upload_max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": {"code": "RESUME_TOO_LARGE", "message": "The uploaded file exceeds the 10 MiB limit"}},
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    try:
        return resume_service.upload(
            db,
            user_id,
            file.filename or "resume",
            file.content_type,
            content,
            is_default,
        )
    except ResumeUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_RESUME_FILE", "message": str(exc)}},
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "RESUME_STORAGE_FAILED", "message": str(exc)}},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "SKILL_EXTRACTION_FAILED", "message": str(exc)}},
        ) from exc


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
def update_resume(resume_id: UUID, payload: ResumeUpdate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    updated = resumes_repo.update(db, user_id, resume_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    db.commit()
    return updated


@router.post("/{resume_id}/confirm-skills")
def confirm_resume_skills(
    resume_id: UUID,
    payload: ConfirmResumeSkills,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    ensure_user(db, user_id)
    try:
        profile = resume_service.confirm_skills(
            db,
            user_id,
            resume_id,
            payload.skills,
            payload.education_fields,
        )
    except ResumeUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_SKILL_SELECTION", "message": str(exc)}},
        ) from exc
    if not profile:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    return profile


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
    resume = resumes_repo.get(db, user_id, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    if resume.file_url.startswith(f"{user_id}/"):
        try:
            resume_storage.delete(resume.file_url)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": {"code": "RESUME_STORAGE_FAILED", "message": str(exc)}},
            ) from exc
    deleted = resumes_repo.delete(db, user_id, resume_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "Resume not found"}})
    db.commit()
    return Response(status_code=204)
