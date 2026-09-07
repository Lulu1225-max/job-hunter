from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.experience import Experience
from app.models.interview import Interview
from app.models.interview_answer import InterviewAnswer
from app.models.interview_question import InterviewQuestion
from app.models.job import Job
from app.models.job_import import JobImport
from app.models.resume import Resume
from app.models.user import User
from app.utils.matching import source_fingerprint
from app.utils.normalization import canonical_status, normalize_text, parse_date
from app.services.matching import analyse_job_match


def ensure_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user:
        return user
    user = User(id=user_id, email="local@jobpilot.dev", display_name="Local User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def serialize_model(model: Any) -> dict[str, Any]:
    data = {column.name: getattr(model, column.name) for column in model.__table__.columns}
    for key, value in list(data.items()):
        if isinstance(value, UUID):
            data[key] = str(value)
        elif isinstance(value, (date, datetime)):
            data[key] = value.isoformat()
    return data


class JobRepository:
    def list(self, db: Session, user_id: UUID, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        query: Select[tuple[Job]] = select(Job).where(or_(Job.user_id == user_id, Job.user_id.is_(None)))
        keyword = filters.get("keyword")
        if keyword:
            pattern = f"%{normalize_text(keyword)}%"
            query = query.where(
                or_(
                    func.lower(Job.company).like(pattern),
                    func.lower(func.coalesce(Job.role, "")).like(pattern),
                    func.lower(func.coalesce(Job.location, "")).like(pattern),
                    func.lower(func.coalesce(Job.industry, "")).like(pattern),
                    func.lower(func.coalesce(Job.description, "")).like(pattern),
                )
            )
        for field in ["company", "role", "location", "industry", "job_type", "graduation_cohort"]:
            value = filters.get(field)
            if value:
                query = query.where(func.lower(func.coalesce(getattr(Job, field), "")).like(f"%{normalize_text(value)}%"))
        sort = filters.get("sort") or "recommended"
        if sort == "deadline":
            query = query.order_by(Job.deadline.asc().nulls_last(), Job.created_at.desc())
        elif sort == "newest":
            query = query.order_by(Job.created_at.desc())
        else:
            query = query.order_by(Job.created_at.desc())
        rows = db.scalars(query.limit(500)).all()
        profile = profile_repo.get(db, user_id)
        resume = resumes_repo.default(db, user_id)
        jobs = [serialize_model(row) for row in rows]
        for job in jobs:
            job["match"] = analyse_job_match(profile, resume, job)
        if sort in {"recommended", "match_score"}:
            jobs.sort(key=lambda item: (item["match"].get("score") is not None, item["match"].get("score") or 0), reverse=True)
        return jobs

    def get(self, db: Session, user_id: UUID, job_id: UUID) -> dict[str, Any] | None:
        row = db.get(Job, job_id)
        if not row or row.user_id not in (user_id, None):
            return None
        return serialize_model(row)

    def upsert(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        source_hash = payload.get("source_hash") or source_fingerprint(
            [payload.get("company"), payload.get("role"), payload.get("location"), payload.get("job_url")]
        )
        values = {**payload, "user_id": user_id, "source_hash": source_hash}
        for key in ["application_open_date", "deadline"]:
            if isinstance(values.get(key), str):
                values[key] = parse_date(values[key])
        stmt = (
            insert(Job)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_jobs_user_source_hash",
                set_={
                    key: value
                    for key, value in values.items()
            if key not in {"id", "user_id", "source_hash"} and value not in (None, "", [])
                }
                | {"updated_at": datetime.now(timezone.utc)},
            )
            .returning(Job)
        )
        row = db.scalars(stmt).one()
        created = row.created_at == row.updated_at
        return serialize_model(row), created

    def existing_hashes(self, db: Session, user_id: UUID) -> set[str]:
        return set(db.scalars(select(Job.source_hash).where(Job.user_id == user_id)).all())

    def record_import(self, db: Session, user_id: UUID, filepath: str, sheet_name: str, counts: dict[str, int]) -> dict[str, Any]:
        row = JobImport(
            user_id=user_id,
            filename=Path(filepath).name,
            sheet_name=sheet_name,
            total_rows=counts["total_rows"],
            created_count=counts["created"],
            updated_count=counts["updated"],
            skipped_count=counts["skipped"],
            invalid_count=counts["invalid"],
        )
        db.add(row)
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

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        values = {"skills": [], "technologies": [], **payload}
        row = Experience(user_id=user_id, **values)
        db.add(row)
        db.flush()
        return serialize_model(row)

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

    def update(self, db: Session, user_id: UUID, experience_id: UUID, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self.get(db, user_id, experience_id)
        if not row:
            return None
        for key, value in payload.items():
            if value is not None:
                setattr(row, key, value)
        db.flush()
        return serialize_model(row)

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
        if not row:
            row = db.scalar(select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc()))
        return serialize_model(row) if row else None

    def create(self, db: Session, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        values = {key: value for key, value in payload.items() if value is not None}
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


class InterviewQuestionRepository:
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
            select(Interview, Application).join(Application, Interview.application_id == Application.id).where(Application.user_id == user_id)
        ).all()
        return [{**serialize_model(interview), "application": serialize_model(application)} for interview, application in rows]

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
        row = Interview(application_id=application_id, **values)
        db.add(row)
        db.flush()
        return row


class InterviewAnswerRepository:
    def create(self, db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        row = InterviewAnswer(**{key: value for key, value in payload.items() if value is not None})
        db.add(row)
        db.flush()
        return serialize_model(row)


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
applications_repo = ApplicationRepository()
profile_repo = ProfileRepository()
experiences_repo = ExperienceRepository()
resumes_repo = ResumeRepository()
interview_questions_repo = InterviewQuestionRepository()
interviews_repo = InterviewRepository()
interview_answers_repo = InterviewAnswerRepository()
analytics_repo = AnalyticsRepository()
