from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.database import jobs_repo
from app.utils.excel import import_sheet, preview_workbook


class JobService:
    def preview_import(self, filepath: str) -> dict:
        return asdict(preview_workbook(Path(filepath)))

    def confirm_import(self, db: Session, user_id: UUID, filepath: str, sheet_name: str) -> dict:
        existing_hashes = jobs_repo.existing_hashes(db, user_id)
        result = import_sheet(Path(filepath), sheet_name, existing_hashes)
        for job in result.jobs:
            jobs_repo.upsert(db, user_id, job.__dict__)
        counts = {
            "total_rows": result.total_rows,
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "invalid": result.invalid,
        }
        import_record = jobs_repo.record_import(db, user_id, filepath, sheet_name, counts)
        db.commit()
        return {**counts, "import": import_record, "issues": [issue.__dict__ for issue in result.issues[:25]]}

    def list_jobs(self, db: Session, user_id: UUID, filters: dict[str, str | None]) -> list[dict]:
        return jobs_repo.list(db, user_id, filters)

    def get_job(self, db: Session, user_id: UUID, job_id: UUID) -> dict | None:
        return jobs_repo.get(db, user_id, job_id)

    def create_job(self, db: Session, user_id: UUID, payload: dict) -> dict:
        job, _ = jobs_repo.upsert(db, user_id, payload)
        db.commit()
        return job


job_service = JobService()
