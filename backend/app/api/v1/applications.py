from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import applications_repo, ensure_user, jobs_repo
from app.schemas.ai import ApplicationEmailParseRequest
from app.schemas.applications import ApplicationCreate, ApplicationUpdate
from app.services.ai.application_parser import application_parser
from app.skills.company_role_research import company_role_research_skill
from app.skills.company_role_research.schemas import CompanyRoleResearchOutput

router = APIRouter()


@router.get("")
def list_applications(
    status: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=100),
    sort: str = "created_at_desc",
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[dict]:
    ensure_user(db, user_id)
    return applications_repo.list(db, user_id, status=status, limit=limit, sort=sort)


@router.post("")
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    values = payload.model_dump()
    if payload.job_id:
        job_id = UUID(payload.job_id)
        job = jobs_repo.get_row(db, user_id, job_id)
        if not job:
            raise HTTPException(status_code=404, detail={"error": {"code": "JOB_NOT_FOUND", "message": "Job not found"}})
        existing = applications_repo.get_by_job_id(db, user_id, job_id)
        if existing:
            return existing
        values["company"] = job.company
        values["role"] = job.role
        if values["job_description"] is None:
            values["job_description"] = job.description
    elif not payload.company:
        raise HTTPException(status_code=422, detail={"error": {"code": "COMPANY_REQUIRED", "message": "Company is required"}})
    application = applications_repo.create(db, user_id, values)
    db.commit()
    return application


@router.get("/{application_id}")
def get_application(application_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    application = applications_repo.get(db, user_id, application_id)
    if not application:
        raise HTTPException(status_code=404, detail={"error": {"code": "APPLICATION_NOT_FOUND", "message": "Application not found"}})
    from app.repositories.database import serialize_model

    return serialize_model(application)


@router.post("/{application_id}/company-research", response_model=CompanyRoleResearchOutput)
def research_company_and_role(
    application_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    regenerate_company_profile: bool = Query(default=False),
) -> CompanyRoleResearchOutput:
    ensure_user(db, user_id)
    application = applications_repo.get(db, user_id, application_id)
    if not application:
        raise HTTPException(status_code=404, detail={"error": {"code": "APPLICATION_NOT_FOUND", "message": "Application not found"}})
    return company_role_research_skill.run(
        db,
        user_id,
        application,
        force_profile_refresh=regenerate_company_profile,
    )


@router.put("/{application_id}")
def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    ensure_user(db, user_id)
    updated = applications_repo.update(db, user_id, application_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail={"error": {"code": "APPLICATION_NOT_FOUND", "message": "Application not found"}})
    db.commit()
    return updated


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> Response:
    ensure_user(db, user_id)
    deleted = applications_repo.delete(db, user_id, application_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": {"code": "APPLICATION_NOT_FOUND", "message": "Application not found"}})
    db.commit()
    return Response(status_code=204)


@router.patch("/{application_id}/status")
def update_status(application_id: UUID, status: str, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    updated = applications_repo.update_status(db, user_id, application_id, status)
    if not updated:
        raise HTTPException(status_code=404, detail={"error": {"code": "APPLICATION_NOT_FOUND", "message": "Application not found"}})
    db.commit()
    return updated


@router.post("/parse-email-preview")
def parse_application_email(payload: ApplicationEmailParseRequest) -> dict:
    return application_parser.parse_preview(payload.text).model_dump()
