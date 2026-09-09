from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.database import profile_repo, resumes_repo
from app.schemas.skills import DetectedSkills
from app.services.ai.skill_extractor import resume_skill_extractor
from app.services.document_parser import DocumentParseError, document_parser
from app.services.storage import resume_storage


ALLOWED_FILE_TYPES = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}


class ResumeUploadError(ValueError):
    pass


class ResumeService:
    def validate_file(self, filename: str, content_type: str | None, content: bytes) -> str:
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix not in ALLOWED_FILE_TYPES:
            raise ResumeUploadError("Only PDF and DOCX files are supported")
        if not content:
            raise ResumeUploadError("The uploaded file is empty")
        if len(content) > settings.resume_upload_max_bytes:
            raise ResumeUploadError("The uploaded file exceeds the 10 MiB limit")
        if content_type and content_type not in ALLOWED_FILE_TYPES[suffix]:
            raise ResumeUploadError("The file MIME type does not match PDF or DOCX")
        if suffix == "pdf" and not content.startswith(b"%PDF-"):
            raise ResumeUploadError("The uploaded file is not a valid PDF")
        if suffix == "docx" and not content.startswith(b"PK"):
            raise ResumeUploadError("The uploaded file is not a valid DOCX")
        return suffix

    def upload(
        self,
        db: Session,
        user_id: UUID,
        filename: str,
        content_type: str | None,
        content: bytes,
        is_default: bool | None,
    ) -> dict:
        file_type = self.validate_file(filename, content_type, content)
        resume_id = uuid4()
        safe_name = self._safe_filename(filename)
        storage_path = f"{user_id}/{resume_id}/{safe_name}"
        stored_path = resume_storage.upload(
            storage_path,
            content,
            "application/pdf"
            if file_type == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        try:
            resumes_repo.create(
                db,
                user_id,
                {
                    "id": resume_id,
                    "name": Path(filename).stem[:250],
                    "file_url": stored_path,
                    "file_type": file_type,
                    "extracted_text": None,
                    "structured_content": {},
                    "detected_skills": DetectedSkills().model_dump(),
                    "is_default": is_default,
                },
            )
            db.commit()
            extracted_text = document_parser.extract_text(content, file_type)
            detected_skills = resume_skill_extractor.extract(extracted_text)
            updated = resumes_repo.update(
                db,
                user_id,
                resume_id,
                {
                    "extracted_text": extracted_text,
                    "detected_skills": detected_skills.model_dump(),
                },
            )
            db.commit()
            if not updated:
                raise RuntimeError("Created resume could not be reloaded")
            return updated
        except DocumentParseError as exc:
            self._remove_failed_upload(db, user_id, resume_id, stored_path)
            raise ResumeUploadError(str(exc)) from exc
        except Exception:
            self._remove_failed_upload(db, user_id, resume_id, stored_path)
            raise

    def confirm_skills(
        self,
        db: Session,
        user_id: UUID,
        resume_id: UUID,
        selected: DetectedSkills,
    ) -> dict | None:
        resume = resumes_repo.get(db, user_id, resume_id)
        if not resume:
            return None
        detected = DetectedSkills.model_validate(resume.detected_skills)
        selected_data = selected.model_dump()
        detected_data = detected.model_dump()
        approved: dict[str, list[str]] = {}
        for category, values in selected_data.items():
            allowed = {value.casefold(): value for value in detected_data[category]}
            if any(value.casefold() not in allowed for value in values):
                raise ResumeUploadError("Selected skills must come from this resume's detected skills")
            approved[category] = [allowed[value.casefold()] for value in values]

        current = profile_repo.get(db, user_id) or {}
        updates = {
            category: self._merge(current.get(category, []), values)
            for category, values in approved.items()
        }
        profile = profile_repo.upsert(db, user_id, updates)
        db.commit()
        return profile

    @staticmethod
    def _merge(existing: list[str], added: list[str]) -> list[str]:
        result = list(existing)
        seen = {value.casefold() for value in existing}
        for value in added:
            if value.casefold() not in seen:
                seen.add(value.casefold())
                result.append(value)
        return result

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
        return cleaned[:180] or "resume"

    @staticmethod
    def _remove_failed_upload(db: Session, user_id: UUID, resume_id: UUID, stored_path: str) -> None:
        db.rollback()
        if resumes_repo.get(db, user_id, resume_id):
            resumes_repo.delete(db, user_id, resume_id)
            db.commit()
        resume_storage.delete(stored_path)


resume_service = ResumeService()
