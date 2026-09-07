from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user, experiences_repo, profile_repo, resumes_repo, serialize_model
from app.schemas.jobs import ImportConfirmRequest, ImportPreviewRequest, JobCreate, JobImportRequest
from app.services.job_service import job_service
from app.services.matching import analyse_resume_match

router = APIRouter()


@router.get("")
def list_jobs_endpoint(
    keyword: str | None = None,
    company: str | None = None,
    role: str | None = None,
    location: str | None = None,
    industry: str | None = None,
    job_type: str | None = None,
    graduation_cohort: str | None = None,
    sort: str | None = "recommended",
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[dict]:
    ensure_user(db, user_id)
    return job_service.list_jobs(
        db,
        user_id,
        {
            "keyword": keyword,
            "company": company,
            "role": role,
            "location": location,
            "industry": industry,
            "job_type": job_type,
            "graduation_cohort": graduation_cohort,
            "sort": sort,
        },
    )


@router.get("/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    job = job_service.get_job(db, user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": {"code": "JOB_NOT_FOUND", "message": "Job not found"}})
    return job


@router.post("")
def create_job(payload: JobCreate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    return job_service.create_job(db, user_id, payload.model_dump())


@router.post("/import")
def import_jobs(payload: JobImportRequest, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    if not payload.confirm:
        return job_service.preview_import(payload.filepath)
    if not payload.sheet_name:
        raise HTTPException(status_code=422, detail={"error": {"code": "SHEET_REQUIRED", "message": "sheet_name is required when confirm is true"}})
    return job_service.confirm_import(db, user_id, payload.filepath, payload.sheet_name)


@router.post("/import/preview")
def preview_import(payload: ImportPreviewRequest) -> dict:
    return job_service.preview_import(payload.filepath)


@router.post("/import/confirm")
def confirm_import(payload: ImportConfirmRequest, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    return job_service.confirm_import(db, user_id, payload.filepath, payload.sheet_name)


@router.post("/{job_id}/match")
def match_job(
    job_id: UUID,
    resume_id: UUID | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    ensure_user(db, user_id)
    job = job_service.get_job(db, user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": {"code": "JOB_NOT_FOUND", "message": "Job not found"}})
    if resume_id:
        resume_row = resumes_repo.get(db, user_id, resume_id)
        resume = None if not resume_row else serialize_model(resume_row)
    else:
        resume = resumes_repo.default(db, user_id)
    if not resume:
        raise HTTPException(status_code=404, detail={"error": {"code": "RESUME_NOT_FOUND", "message": "No resume found"}})
    return analyse_resume_match(profile_repo.get(db, user_id), resume, job, experiences_repo.list(db, user_id))
