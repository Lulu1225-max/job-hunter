from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.experience import Experience
from app.models.interview import Interview
from app.models.interview_answer import InterviewAnswer
from app.models.interview_question import InterviewQuestion
from app.models.job import Job
from app.models.job_import import JobImport
from app.models.resume import Resume
from app.models.resume_analysis import ResumeAnalysis
from app.repositories.database import ensure_user
from app.scripts.seed_demo_applications import PROFILE, get_demo_user_identity, seed_demo_state
from app.services.storage import resume_storage


def clear_demo_data(db, demo_user_id: UUID) -> list[str]:
    """Delete only data owned by the configured demo UUID, in dependency order."""
    stored_paths = list(db.scalars(select(Resume.file_url).where(Resume.user_id == demo_user_id)).all())
    question_ids = select(InterviewQuestion.id).where(InterviewQuestion.user_id == demo_user_id)
    application_ids = select(Application.id).where(Application.user_id == demo_user_id)
    db.execute(delete(InterviewAnswer).where(InterviewAnswer.question_id.in_(question_ids)))
    db.execute(delete(Interview).where(Interview.application_id.in_(application_ids)))
    db.execute(delete(InterviewQuestion).where(InterviewQuestion.user_id == demo_user_id))
    db.execute(delete(ResumeAnalysis).where(ResumeAnalysis.user_id == demo_user_id))
    db.execute(delete(Application).where(Application.user_id == demo_user_id))
    db.execute(delete(JobImport).where(JobImport.user_id == demo_user_id))
    db.execute(delete(Resume).where(Resume.user_id == demo_user_id))
    db.execute(delete(Experience).where(Experience.user_id == demo_user_id))
    db.execute(delete(Job).where(Job.user_id == demo_user_id))
    db.execute(delete(CareerProfile).where(CareerProfile.user_id == demo_user_id))
    db.flush()
    prefix = f"{demo_user_id}/"
    return [path for path in stored_paths if path and path.startswith(prefix)]


def reset_demo(db, demo_user_id: UUID, demo_email: str | None, *, storage=resume_storage) -> None:
    # Synchronize the local user first; ensure_user may commit when account metadata changed.
    ensure_user(db, demo_user_id, email=demo_email, display_name=PROFILE["display_name"])
    paths = clear_demo_data(db, demo_user_id)
    for path in paths:
        storage.delete(path)
    seed_demo_state(db, demo_user_id, demo_email)
    db.commit()


def main() -> None:
    demo_user_id, demo_email = get_demo_user_identity()
    print("Demo user resolved")
    db = SessionLocal()
    try:
        reset_demo(db, demo_user_id, demo_email)
        print("Old demo data cleared")
        print("Canonical demo seed restored")
        print("Demo reset complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
