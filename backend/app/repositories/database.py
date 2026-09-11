from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.discovery_match_cache import DiscoveryMatchCache
from app.models.experience import Experience
from app.models.interview import Interview
from app.models.interview_answer import InterviewAnswer
from app.models.interview_question import InterviewQuestion
from app.models.job import Job
from app.models.job_import import JobImport
from app.models.resume import Resume
from app.models.resume_analysis import ResumeAnalysis
from app.models.user import User
from app.utils.matching import source_fingerprint
from app.utils.normalization import canonical_status, normalize_text, parse_date


def ensure_user(db: Session, user_id: UUID, email: str | None = None, display_name: str | None = None) -> User:
    user = db.get(User, user_id)
    if user:
        changed = False
        if email and user.email != email:
            user.email = email
            changed = True
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
        return user
    user = User(id=user_id, email=email or f"{user_id}@supabase.local", display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def serialize_model(model: Any) -> dict[str, Any]:
    data = {column.name: getattr(model, column.name) for column in model.__table__.columns if column.name not in {"embedding", "embedding_fingerprint"}}
    for key, value in list(data.items()):
        if isinstance(value, UUID):
            data[key] = str(value)
        elif isinstance(value, (date, datetime)):
            data[key] = value.isoformat()
    return data


class JobRepository:
    ALLOWED = {"company", "role", "location", "job_url", "salary", "description", "industry", "job_type", "deadline",
               "application_start_date", "campus_category", "referral_available", "graduation_cohort", "company_type",
               "technical_skills", "product_skills", "soft_skills",
               "required_skills", "education_requirements", "external_id"}

    def _filtered(self, user_id: UUID, filters: dict[str, Any]):
        query = select(Job).where(Job.user_id == user_id)
        keyword = filters.get("q") or filters.get("keyword")
        if keyword:
            pattern = f"%{normalize_text(keyword)}%"
            query = query.where(or_(func.lower(Job.company).like(pattern), func.lower(func.coalesce(Job.role, "")).like(pattern), func.lower(func.coalesce(Job.location, "")).like(pattern), func.lower(func.coalesce(Job.industry, "")).like(pattern), func.lower(func.coalesce(Job.graduation_cohort, "")).like(pattern)))
        for field in ["company", "role", "location", "industry", "job_type"]:
            if filters.get(field): query = query.where(func.lower(func.coalesce(getattr(Job, field), "")).like(f"%{normalize_text(filters[field])}%"))
        return query

    def list(self, db: Session, user_id: UUID, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query = self._filtered(user_id, filters)
        if filters.get("sort") == "deadline": query = query.order_by(Job.deadline.asc().nulls_last(), Job.created_at.desc())
        else: query = query.order_by(Job.created_at.desc())
        return [serialize_model(row) for row in db.scalars(query.limit(500)).all()]

    def page(self, db: Session, user_id: UUID, filters: dict[str, Any], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        filtered = self._filtered(user_id, filters)
        total = db.scalar(select(func.count()).select_from(filtered.order_by(None).subquery())) or 0
        if filters.get("sort") == "deadline": filtered = filtered.order_by(Job.deadline.asc().nulls_last(), Job.created_at.desc())
        else: filtered = filtered.order_by(Job.created_at.desc())
        rows = db.scalars(filtered.offset((page - 1) * page_size).limit(page_size)).all()
        return [serialize_model(row) for row in rows], total

    def get_row(self, db: Session, user_id: UUID, job_id: UUID) -> Job | None:
        row = db.get(Job, job_id)
        return row if row and row.user_id == user_id else None

    def get(self, db: Session, user_id: UUID, job_id: UUID) -> dict[str, Any] | None:
        row = self.get_row(db, user_id, job_id)
        return serialize_model(row) if row else None

    def _clean(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = {k: v for k, v in payload.items() if k in self.ALLOWED and v is not None}
        for key in ("deadline", "application_start_date"):
            if isinstance(values.get(key), str): values[key] = parse_date(values[key])
        return values

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        values = self._clean(payload)
        source_hash = source_fingerprint([values.get(k) for k in ("company", "role", "location", "job_url", "deadline", "description")] + [str(uuid4())])
        row = Job(user_id=user_id, source="manual", source_hash=source_hash, **values)
        db.add(row); db.flush(); return serialize_model(row)

    def update(self, db: Session, user_id: UUID, job_id: UUID, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self.get_row(db, user_id, job_id)
        if not row: return None
        for key, value in self._clean(payload).items(): setattr(row, key, value)
        db.flush(); return serialize_model(row)

    def delete(self, db: Session, user_id: UUID, job_id: UUID) -> bool:
        row = self.get_row(db, user_id, job_id)
        if not row: return False
        db.delete(row); db.flush(); return True

    def import_upsert(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> str:
        source_hash = payload.get("source_hash") or source_fingerprint(
            [payload.get(k) for k in ("company", "role", "location", "job_url", "deadline", "description")]
        )
        existing = db.scalar(select(Job).where(Job.user_id == user_id, Job.source_hash == source_hash))
        values = self._clean(payload)
        if not existing:
            db.add(Job(user_id=user_id, source=payload.get("source", "import"), source_hash=source_hash, **values)); db.flush(); return "created"
        changed = False
        for key, value in values.items():
            if value not in (None, "", []) and getattr(existing, key) != value: setattr(existing, key, value); changed = True
        if changed: existing.updated_at = datetime.now(timezone.utc); db.flush(); return "updated"
        return "skipped"

    def upsert(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        status = self.import_upsert(db, user_id, payload)
        source_hash = payload.get("source_hash") or source_fingerprint(
            [payload.get(k) for k in ("company", "role", "location", "job_url", "deadline", "description")]
        )
        row = db.scalar(select(Job).where(Job.user_id == user_id, Job.source_hash == source_hash))
        return serialize_model(row), status == "created"

    def existing_hashes(self, db: Session, user_id: UUID) -> set[str]:
        return set(db.scalars(select(Job.source_hash).where(Job.user_id == user_id)).all())

    def record_import(self, db: Session, user_id: UUID, filepath: str, sheet_name: str, counts: dict[str, int]) -> dict[str, Any]:
        row = JobImport(user_id=user_id, filename=Path(filepath).name, sheet_name=sheet_name, total_rows=counts["total_rows"], created_count=counts["created"], updated_count=counts["updated"], skipped_count=counts["skipped"], invalid_count=counts["invalid"])
        db.add(row); db.flush(); return serialize_model(row)


class JobImportPreviewRepository:
    def create(self, db: Session, user_id: UUID, filename: str, content: bytes, preview_payload: dict, expires_at: datetime) -> JobImport:
        row = JobImport(user_id=user_id, filename=Path(filename).name, sheet_name="", status="preview",
                        file_content=content, preview_payload=preview_payload, expires_at=expires_at)
        db.add(row)
        db.flush()
        return row

    def get(self, db: Session, user_id: UUID, preview_id: UUID, *, lock: bool = False) -> JobImport | None:
        query = select(JobImport).where(JobImport.id == preview_id, JobImport.user_id == user_id)
        if lock:
            query = query.with_for_update(nowait=True)
        return db.scalar(query)

    def save_options(self, db: Session, row: JobImport, options: dict) -> None:
        row.preview_payload = {**(row.preview_payload or {}), "selected_options": options}
        db.flush()

    def confirm(self, db: Session, row: JobImport, sheet_name: str, counts: dict[str, int]) -> dict[str, Any]:
        row.sheet_name = sheet_name
        row.status = "confirmed"
        row.imported_at = datetime.now(timezone.utc)
        row.total_rows = counts["total_rows"]
        row.created_count = counts["created"]
        row.updated_count = counts["updated"]
        row.skipped_count = counts["skipped"]
        row.invalid_count = counts["invalid"]
        row.file_content = None
        db.flush()
        return serialize_model(row)


class ApplicationRepository:
    def list(
        self,
        db: Session,
        user_id: UUID,
        status: str | None = None,
        limit: int | None = None,
        sort: str = "created_at_desc",
    ) -> list[dict[str, Any]]:
        query = select(Application).where(Application.user_id == user_id)
        if status:
            query = query.where(Application.status == canonical_status(status))
        order_column = Application.updated_at if sort == "updated_at_desc" else Application.created_at
        query = query.order_by(order_column.desc())
        if limit:
            query = query.limit(min(max(limit, 1), 100))
        rows = db.scalars(query).all()
        return [serialize_model(row) for row in rows]

    def get_seed(self, db: Session, user_id: UUID, company: str, role: str) -> Application | None:
        return db.scalar(
            select(Application).where(
                Application.user_id == user_id,
                Application.source == "seed_demo",
                Application.company == company,
                Application.role == role,
            )
        )

    def upsert_seed(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_seed(db, user_id, payload["company"], payload["role"])
        if existing:
            for key, value in self._clean(payload).items():
                setattr(existing, key, value)
            db.flush()
            return serialize_model(existing)
        return self.create(db, user_id, payload)

    def get(self, db: Session, user_id: UUID, application_id: UUID) -> Application | None:
        row = db.get(Application, application_id)
        return row if row and row.user_id == user_id else None

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        values = self._clean(payload)
        row = Application(user_id=user_id, **values)
        db.add(row)
        db.flush()
        return serialize_model(row)

    def update(self, db: Session, user_id: UUID, application_id: UUID, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self.get(db, user_id, application_id)
        if not row:
            return None
        for key, value in self._clean(payload).items():
            setattr(row, key, value)
        db.flush()
        return serialize_model(row)

    def delete(self, db: Session, user_id: UUID, application_id: UUID) -> bool:
        row = self.get(db, user_id, application_id)
        if not row:
            return False
        db.delete(row)
        db.flush()
        return True

    def update_status(self, db: Session, user_id: UUID, application_id: UUID, status: str) -> dict[str, Any] | None:
        return self.update(db, user_id, application_id, {"status": status})

    def _clean(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = {key: value for key, value in payload.items() if value is not None}
        if "status" in values:
            values["status"] = canonical_status(values.get("status"))
        for key in ["application_date", "deadline"]:
            if isinstance(values.get(key), str):
                values[key] = parse_date(values[key])
        return values


class ProfileRepository:
    def get(self, db: Session, user_id: UUID) -> dict[str, Any] | None:
        row = db.scalar(select(CareerProfile).where(CareerProfile.user_id == user_id))
        return serialize_model(row) if row else None

    def upsert(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        existing = db.scalar(select(CareerProfile).where(CareerProfile.user_id == user_id))
        values = {key: value for key, value in payload.items() if value is not None}
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            db.flush()
            return serialize_model(existing)
        row = CareerProfile(
            user_id=user_id,
            target_roles=values.pop("target_roles", []),
            target_locations=values.pop("target_locations", []),
            target_industries=values.pop("target_industries", []),
            preferred_job_types=values.pop("preferred_job_types", []),
            technical_skills=values.pop("technical_skills", []),
            product_skills=values.pop("product_skills", []),
            soft_skills=values.pop("soft_skills", []),
            tools=values.pop("tools", []),
            languages=values.pop("languages", []),
            **values,
        )
        db.add(row)
        db.flush()
        return serialize_model(row)


class ExperienceRepository:
    def list(self, db: Session, user_id: UUID) -> list[dict[str, Any]]:
        rows = db.scalars(select(Experience).where(Experience.user_id == user_id).order_by(Experience.created_at.desc())).all()
        return [serialize_model(row) for row in rows]

    def get(self, db: Session, user_id: UUID, experience_id: UUID) -> Experience | None:
        row = db.get(Experience, experience_id)
        return row if row and row.user_id == user_id else None

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> Experience:
        values = {"skills": [], "technologies": [], **payload}
        row = Experience(user_id=user_id, **values)
        db.add(row)
        db.flush()
        return row

    def search(self, db: Session, user_id: UUID, query: str) -> list[dict[str, Any]]:
        pattern = f"%{normalize_text(query)}%"
        rows = db.scalars(
            select(Experience)
            .where(Experience.user_id == user_id)
            .where(
                or_(
                    func.lower(Experience.title).like(pattern),
                    func.lower(func.coalesce(Experience.description, "")).like(pattern),
                    func.lower(func.coalesce(Experience.situation, "")).like(pattern),
                    func.lower(func.coalesce(Experience.task, "")).like(pattern),
                    func.lower(func.coalesce(Experience.action, "")).like(pattern),
                    func.lower(func.coalesce(Experience.result, "")).like(pattern),
                )
            )
        ).all()
        return [serialize_model(row) for row in rows]

    def update(self, db: Session, user_id: UUID, experience_id: UUID, payload: dict[str, Any]) -> Experience | None:
        row = self.get(db, user_id, experience_id)
        if not row:
            return None
        meaningful = {"title", "type", "description", "situation", "task", "action", "result", "reflection", "skills", "technologies"}
        embedding_stale = any(key in meaningful and getattr(row, key) != value for key, value in payload.items() if value is not None)
        for key, value in payload.items():
            if value is not None:
                setattr(row, key, value)
        if embedding_stale:
            row.embedding = None
            row.embedding_fingerprint = None
        db.flush()
        return row

    def missing_embeddings(self, db: Session, user_id: UUID, limit: int) -> list[Experience]:
        return list(db.scalars(select(Experience).where(
            Experience.user_id == user_id,
            Experience.embedding.is_(None),
        ).order_by(Experience.updated_at.desc()).limit(limit)).all())

    def vector_search(self, db: Session, user_id: UUID, query_embedding: list[float], limit: int) -> list[tuple[Experience, float]]:
        distance = Experience.embedding.cosine_distance(query_embedding).label("distance")
        statement = select(Experience, distance).where(
            Experience.user_id == user_id,
            Experience.embedding.is_not(None),
        ).order_by(distance).limit(limit)
        return [(row, float(value)) for row, value in db.execute(statement).all()]

    def delete(self, db: Session, user_id: UUID, experience_id: UUID) -> bool:
        row = self.get(db, user_id, experience_id)
        if not row:
            return False
        db.delete(row)
        db.flush()
        return True


class ResumeRepository:
    def list(self, db: Session, user_id: UUID) -> list[dict[str, Any]]:
        rows = db.scalars(select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())).all()
        return [serialize_model(row) for row in rows]

    def get(self, db: Session, user_id: UUID, resume_id: UUID) -> Resume | None:
        row = db.get(Resume, resume_id)
        return row if row and row.user_id == user_id else None

    def default(self, db: Session, user_id: UUID) -> dict[str, Any] | None:
        row = db.scalar(select(Resume).where(Resume.user_id == user_id, Resume.is_default.is_(True)))
        return serialize_model(row) if row else None

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        values = {key: value for key, value in payload.items() if value is not None}
        values.setdefault("file_type", "pdf")
        values.setdefault(
            "detected_skills",
            {
                "education": {
                    "university": None,
                    "degree": None,
                    "major": None,
                    "specialisation": None,
                    "graduation_year": None,
                },
                "technical_skills": [],
                "product_skills": [],
                "soft_skills": [],
                "tools": [],
                "languages": [],
            },
        )
        if values.get("is_default"):
            self._clear_default(db, user_id)
        elif "is_default" not in values:
            values["is_default"] = db.scalar(select(func.count(Resume.id)).where(Resume.user_id == user_id)) == 0
        row = Resume(user_id=user_id, **values)
        db.add(row)
        db.flush()
        return serialize_model(row)

    def update(self, db: Session, user_id: UUID, resume_id: UUID, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self.get(db, user_id, resume_id)
        if not row:
            return None
        values = {key: value for key, value in payload.items() if value is not None}
        if values.get("is_default"):
            self._clear_default(db, user_id)
        for key, value in values.items():
            setattr(row, key, value)
        db.flush()
        return serialize_model(row)

    def delete(self, db: Session, user_id: UUID, resume_id: UUID) -> bool:
        row = self.get(db, user_id, resume_id)
        if not row:
            return False
        db.delete(row)
        db.flush()
        return True

    def set_default(self, db: Session, user_id: UUID, resume_id: UUID) -> dict[str, Any] | None:
        row = self.get(db, user_id, resume_id)
        if not row:
            return None
        self._clear_default(db, user_id)
        row.is_default = True
        db.flush()
        return serialize_model(row)

    def _clear_default(self, db: Session, user_id: UUID) -> None:
        rows = db.scalars(select(Resume).where(Resume.user_id == user_id, Resume.is_default.is_(True))).all()
        for row in rows:
            row.is_default = False


class ResumeAnalysisRepository:
    def current(self, db: Session, user_id: UUID, resume_id: UUID, job_id: UUID, resume_fingerprint: str, job_fingerprint: str, version: str, response_language: str) -> ResumeAnalysis | None:
        return db.scalar(select(ResumeAnalysis).where(
            ResumeAnalysis.user_id == user_id,
            ResumeAnalysis.resume_id == resume_id,
            ResumeAnalysis.job_id == job_id,
            ResumeAnalysis.resume_fingerprint == resume_fingerprint,
            ResumeAnalysis.job_fingerprint == job_fingerprint,
            ResumeAnalysis.analysis_version == version,
            ResumeAnalysis.response_language == response_language,
        ).order_by(ResumeAnalysis.created_at.desc()))

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> ResumeAnalysis:
        row = ResumeAnalysis(user_id=user_id, **payload)
        db.add(row)
        db.flush()
        return row


class DiscoveryMatchCacheRepository:
    def current(self, db: Session, user_id: UUID, resume_id: UUID, job_id: UUID, resume_fingerprint: str, job_fingerprint: str, scoring_version: str) -> DiscoveryMatchCache | None:
        return db.scalar(select(DiscoveryMatchCache).where(
            DiscoveryMatchCache.user_id == user_id,
            DiscoveryMatchCache.resume_id == resume_id,
            DiscoveryMatchCache.job_id == job_id,
            DiscoveryMatchCache.resume_fingerprint == resume_fingerprint,
            DiscoveryMatchCache.job_fingerprint == job_fingerprint,
            DiscoveryMatchCache.scoring_version == scoring_version,
        ))

    def create(self, db: Session, user_id: UUID, resume_id: UUID, job_id: UUID, resume_fingerprint: str, job_fingerprint: str, scoring_version: str, result: dict[str, Any]) -> DiscoveryMatchCache:
        row = DiscoveryMatchCache(
            user_id=user_id, resume_id=resume_id, job_id=job_id,
            resume_fingerprint=resume_fingerprint, job_fingerprint=job_fingerprint,
            scoring_version=scoring_version, status=result["status"], result_payload=result,
        )
        db.add(row)
        db.flush()
        return row


class InterviewQuestionRepository:
    def list(self, db: Session, user_id: UUID, category: str | None = None, source: str | None = None, application_id: UUID | None = None) -> list[dict[str, Any]]:
        query=select(InterviewQuestion).where(InterviewQuestion.user_id==user_id)
        if category: query=query.where(InterviewQuestion.category==category)
        if source: query=query.where(InterviewQuestion.source==source)
        if application_id: query=query.where(InterviewQuestion.application_id==application_id)
        return [serialize_model(row) for row in db.scalars(query.order_by(InterviewQuestion.created_at.desc())).all()]
    def list_for_application(self, db: Session, user_id: UUID, application_id: UUID) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(InterviewQuestion)
            .where(InterviewQuestion.user_id == user_id, InterviewQuestion.application_id == application_id)
            .order_by(InterviewQuestion.created_at.asc())
        ).all()
        return [serialize_model(row) for row in rows]

    def get(self, db: Session, user_id: UUID, question_id: UUID) -> InterviewQuestion | None:
        row = db.get(InterviewQuestion, question_id)
        return row if row and row.user_id == user_id else None

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        values = {key: value for key, value in payload.items() if value is not None}
        row = InterviewQuestion(user_id=user_id, **values)
        db.add(row)
        db.flush()
        return serialize_model(row)

    def upsert_seed(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        existing = db.scalar(
            select(InterviewQuestion).where(
                InterviewQuestion.user_id == user_id,
                InterviewQuestion.application_id == payload.get("application_id"),
                InterviewQuestion.question == payload["question"],
                InterviewQuestion.source == payload.get("source", "user_added"),
            )
        )
        if existing:
            for key, value in payload.items():
                if value is not None:
                    setattr(existing, key, value)
            db.flush()
            return serialize_model(existing)
        return self.create(db, user_id, payload)


class InterviewRepository:
    def list(self, db: Session, user_id: UUID) -> list[dict[str, Any]]:
        rows = db.execute(
            select(Interview, Application).join(Application, Interview.application_id == Application.id).where(Interview.user_id == user_id,Application.user_id == user_id).order_by(Interview.created_at.desc())
        ).all()
        ids=[interview.id for interview,_ in rows]
        questions=db.scalars(select(InterviewQuestion).where(InterviewQuestion.user_id==user_id,InterviewQuestion.interview_id.in_(ids),InterviewQuestion.source=="actual_interview")).all() if ids else []
        grouped:dict[UUID,list[dict[str,Any]]]={}
        for question in questions:grouped.setdefault(question.interview_id,[]).append(serialize_model(question))
        return [{**serialize_model(interview), "application": serialize_model(application),"actual_questions":grouped.get(interview.id,[])} for interview, application in rows]

    def get(self, db: Session, user_id: UUID, interview_id: UUID) -> Interview | None:
        return db.scalar(select(Interview).where(Interview.id==interview_id,Interview.user_id==user_id))

    def create(self, db: Session, user_id: UUID, application_id: UUID, payload: dict[str, Any]) -> Interview:
        row=Interview(user_id=user_id,application_id=application_id,**{k:v for k,v in payload.items() if v is not None})
        db.add(row);db.flush();return row

    def update(self, db: Session, user_id: UUID, interview_id: UUID, payload: dict[str, Any]) -> Interview | None:
        row=self.get(db,user_id,interview_id)
        if not row:return None
        for key,value in payload.items():
            if value is not None:setattr(row,key,value)
        db.flush();return row

    def delete(self, db: Session, user_id: UUID, interview_id: UUID) -> bool:
        row=self.get(db,user_id,interview_id)
        if not row:return False
        db.delete(row);db.flush();return True

    def get_by_application(self, db: Session, user_id: UUID, application_id: UUID) -> dict[str, Any] | None:
        row = db.execute(
            select(Interview, Application)
            .join(Application, Interview.application_id == Application.id)
            .where(Application.user_id == user_id, Interview.application_id == application_id)
        ).first()
        if not row:
            return None
        interview, application = row
        return {**serialize_model(interview), "application": serialize_model(application)}

    def upsert_seed(self, db: Session, application_id: UUID, payload: dict[str, Any]) -> Interview:
        existing = db.scalar(select(Interview).where(Interview.application_id == application_id))
        values = {key: value for key, value in payload.items() if value is not None}
        if isinstance(values.get("scheduled_at"), str):
            values["scheduled_at"] = datetime.fromisoformat(values["scheduled_at"])
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            db.flush()
            return existing
        application=db.get(Application,application_id)
        row = Interview(user_id=application.user_id,application_id=application_id, **values)
        db.add(row)
        db.flush()
        return row


class InterviewAnswerRepository:
    def current(self,db:Session,user_id:UUID,question_id:UUID,experience_id:UUID|None,question_hash:str,experience_hash:str|None,job_hash:str,language:str,version:str)->InterviewAnswer|None:
        return db.scalar(select(InterviewAnswer).where(InterviewAnswer.user_id==user_id,InterviewAnswer.question_id==question_id,InterviewAnswer.experience_id==experience_id,InterviewAnswer.question_fingerprint==question_hash,InterviewAnswer.experience_fingerprint==experience_hash,InterviewAnswer.job_fingerprint==job_hash,InterviewAnswer.response_language==language,InterviewAnswer.answer_version==version).order_by(InterviewAnswer.created_at.desc()))

    def get(self,db:Session,user_id:UUID,answer_id:UUID)->InterviewAnswer|None:
        return db.scalar(select(InterviewAnswer).where(InterviewAnswer.id==answer_id,InterviewAnswer.user_id==user_id))

    def create(self, db: Session, payload: dict[str, Any]) -> InterviewAnswer:
        row = InterviewAnswer(**{key: value for key, value in payload.items() if value is not None})
        db.add(row)
        db.flush()
        return row


class AnalyticsRepository:
    def overview(self, db: Session, user_id: UUID) -> dict[str, Any]:
        applications = db.scalars(select(Application).where(Application.user_id == user_id)).all()
        status_counts: dict[str, int] = {}
        for app in applications:
            status_counts[app.status] = status_counts.get(app.status, 0) + 1
        today = date.today()
        upcoming_deadlines = sum(1 for app in applications if app.deadline and app.deadline >= today)
        return {
            "applications_count": len(applications),
            "interviews_count": status_counts.get("interview", 0) + status_counts.get("final_interview", 0),
            "offers_count": status_counts.get("offer", 0),
            "rejections_count": status_counts.get("rejected", 0),
            "upcoming_deadlines": upcoming_deadlines,
            "applications_by_status": status_counts,
        }


jobs_repo = JobRepository()
job_import_previews_repo = JobImportPreviewRepository()
applications_repo = ApplicationRepository()
profile_repo = ProfileRepository()
experiences_repo = ExperienceRepository()
resumes_repo = ResumeRepository()
resume_analyses_repo = ResumeAnalysisRepository()
discovery_match_caches_repo = DiscoveryMatchCacheRepository()
interview_questions_repo = InterviewQuestionRepository()
interviews_repo = InterviewRepository()
interview_answers_repo = InterviewAnswerRepository()
analytics_repo = AnalyticsRepository()
