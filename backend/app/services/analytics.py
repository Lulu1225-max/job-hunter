"""Small, best-effort event writer. Never accepts free-form content fields."""
import logging
from time import perf_counter
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.analytics_event import AnalyticsEvent
from app.models.user import User

logger = logging.getLogger(__name__)
EVENTS = {
    "job_created": {"source"},
    "job_imported": {"source", "imported_count", "skipped_count", "duplicate_count"},
    "resume_match_started": {"language", "match_mode"},
    "resume_match_completed": {"cache_hit", "language"},
    "resume_match_failed": set(),
    "experience_retrieved": {"candidate_count", "returned_count"},
    "experience_selected": set(),
    "interview_answer_generated": {"language"},
    "interview_answer_regenerated": {"language"},
}


def elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def track_event(*, db=None, user_id: UUID, event_name: str, job_id: UUID | None = None,
                resume_id: UUID | None = None, experience_id: UUID | None = None,
                status: str | None = None, error_type: str | None = None,
                latency_ms: int | None = None, metadata: dict | None = None) -> None:
    if event_name not in EVENTS:
        raise ValueError("Unknown analytics event")
    # A separate transaction prevents an analytics failure from poisoning the business session.
    try:
        with SessionLocal.begin() as session:
            email = session.scalar(select(User.email).where(User.id == user_id))
            safe_metadata = {key: value for key, value in (metadata or {}).items() if key in EVENTS[event_name]}
            safe_metadata["is_demo"] = bool(settings.demo_user_email and email and email.casefold() == settings.demo_user_email.casefold())
            session.add(AnalyticsEvent(user_id=user_id, event_name=event_name, job_id=job_id,
                                       resume_id=resume_id, experience_id=experience_id,
                                       status=status, error_type=error_type, latency_ms=latency_ms,
                                       event_metadata=safe_metadata))
    except Exception:
        logger.exception("Analytics event write failed: %s", event_name)
