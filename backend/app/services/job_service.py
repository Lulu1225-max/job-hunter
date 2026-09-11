from __future__ import annotations
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from app.repositories.database import job_import_previews_repo, jobs_repo
from app.utils.excel import inspect_import, parse_import

MAX_IMPORT_BYTES = 10 * 1024 * 1024
SESSION_TTL = timedelta(minutes=30)


class JobService:
    def _preview(self, db: Session, preview_id: str, user_id: UUID, *, lock: bool = False):
        try:
            identifier = UUID(preview_id)
        except ValueError as exc:
            raise KeyError("Import preview not found or expired") from exc
        row = job_import_previews_repo.get(db, user_id, identifier, lock=lock)
        if not row or row.status != "preview" or not row.file_content:
            raise KeyError("Import preview not found or expired")
        expires_at = row.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            row.status = "expired"
            row.file_content = None
            db.commit()
            raise KeyError("Import preview not found or expired")
        return row

    def create_preview(self, db: Session, user_id: UUID, filename: str, content: bytes) -> dict:
        if not content:
            raise ValueError("Import file is empty")
        if len(content) > MAX_IMPORT_BYTES:
            raise ValueError("Import file exceeds the 10 MB limit")
        result = inspect_import(content, filename)
        try:
            row = job_import_previews_repo.create(
                db, user_id, filename, content, result, datetime.now(timezone.utc) + SESSION_TTL
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {**result, "preview_id": str(row.id), "max_bytes": MAX_IMPORT_BYTES}

    def preview_rows(self, db: Session, user_id: UUID, preview_id: str, options: dict) -> dict:
        try:
            row = self._preview(db, preview_id, user_id)
            parsed = parse_import(row.file_content, row.filename, options["sheet_name"], options["header_row"], options["mapping"])
            job_import_previews_repo.save_options(db, row, options)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {key: value for key, value in parsed.items() if key != "jobs"}

    def confirm_import(self, db: Session, user_id: UUID, preview_id: str, options: dict) -> dict:
        try:
            row = self._preview(db, preview_id, user_id, lock=True)
            parsed = parse_import(row.file_content, row.filename, options["sheet_name"], options["header_row"], options["mapping"])
            counts = {"total_rows": parsed["total_rows"], "created": 0, "updated": 0,
                      "skipped": parsed["skipped_blank"], "invalid": parsed["invalid"]}
            for payload in parsed["jobs"]:
                counts[jobs_repo.import_upsert(db, user_id, payload)] += 1
            record = job_import_previews_repo.confirm(db, row, options["sheet_name"], counts)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {**counts, "import": record, "issues": parsed["issues"], "warnings": parsed["warnings"]}

    def list_jobs(self, db: Session, user_id: UUID, filters: dict): return jobs_repo.list(db, user_id, filters)
    def page_jobs(self, db: Session, user_id: UUID, filters: dict, page: int, page_size: int): return jobs_repo.page(db, user_id, filters, page, page_size)
    def get_job(self, db: Session, user_id: UUID, job_id: UUID): return jobs_repo.get(db, user_id, job_id)
    def create_job(self, db: Session, user_id: UUID, payload: dict):
        job = jobs_repo.create(db, user_id, payload); db.commit(); return job
    def update_job(self, db: Session, user_id: UUID, job_id: UUID, payload: dict):
        job = jobs_repo.update(db, user_id, job_id, payload); db.commit(); return job
    def delete_job(self, db: Session, user_id: UUID, job_id: UUID):
        deleted = jobs_repo.delete(db, user_id, job_id); db.commit(); return deleted


job_service = JobService()
