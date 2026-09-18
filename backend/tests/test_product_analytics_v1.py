from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import analytics as analytics_module
from app.services import job_service as job_module
from app.api.v1 import jobs as jobs_api
from app.models.analytics_event import AnalyticsEvent


def test_event_writer_allowlists_metadata_and_marks_demo(monkeypatch):
    written = []
    class Session:
        def scalar(self, statement): return "demo@example.com"
        def add(self, event): written.append(event)
    @contextmanager
    def begin(): yield Session()
    monkeypatch.setattr(analytics_module.SessionLocal, "begin", begin)
    monkeypatch.setattr(analytics_module.settings, "demo_user_email", "demo@example.com")
    analytics_module.track_event(user_id=uuid4(), event_name="resume_match_completed", status="success",
                                metadata={"cache_hit": True, "resume_text": "PRIVATE BODY"})
    assert written[0].event_metadata == {"cache_hit": True, "is_demo": True}
    assert "PRIVATE BODY" not in repr(written[0].event_metadata)


def test_event_schema_preserves_history_on_entity_deletion():
    table = AnalyticsEvent.__table__
    for field in ("job_id", "resume_id", "experience_id"):
        assert table.c[field].nullable
        assert next(iter(table.c[field].foreign_keys)).ondelete == "SET NULL"
    assert next(iter(table.c.user_id.foreign_keys)).ondelete == "CASCADE"
    assert not table.c.event_name.nullable


def test_event_write_failure_is_best_effort(monkeypatch):
    @contextmanager
    def broken(): raise RuntimeError("database down"); yield
    monkeypatch.setattr(analytics_module.SessionLocal, "begin", broken)
    analytics_module.track_event(user_id=uuid4(), event_name="job_created")


def test_manual_job_event_after_commit(monkeypatch):
    owner, job_id = uuid4(), uuid4()
    calls = []
    class Db:
        def commit(self): calls.append("commit")
    monkeypatch.setattr(job_module.jobs_repo, "create", lambda *args: {"id": str(job_id)})
    monkeypatch.setattr(job_module, "track_event", lambda **kw: calls.append(kw))
    job_module.job_service.create_job(Db(), owner, {"company": "Example", "description": "PRIVATE JD"})
    assert calls[0] == "commit"
    assert calls[1]["event_name"] == "job_created" and calls[1]["job_id"] == job_id
    assert "PRIVATE JD" not in repr(calls[1])


def test_manual_job_survives_tracking_failure(monkeypatch):
    job_id = uuid4()
    class Db:
        committed = False
        def commit(self): self.committed = True
    db = Db()
    monkeypatch.setattr(job_module.jobs_repo, "create", lambda *args: {"id": str(job_id)})
    monkeypatch.setattr(job_module, "track_event", analytics_module.track_event)
    @contextmanager
    def broken(): raise RuntimeError("analytics unavailable"); yield
    monkeypatch.setattr(analytics_module.SessionLocal, "begin", broken)
    assert job_module.job_service.create_job(db, uuid4(), {})["id"] == str(job_id)
    assert db.committed


def test_match_success_and_failure_events(monkeypatch):
    owner, job_id, resume_id = uuid4(), uuid4(), uuid4()
    events = []
    monkeypatch.setattr(jobs_api, "ensure_user", lambda *args: None)
    monkeypatch.setattr(jobs_api, "track_event", lambda **kw: events.append(kw))
    monkeypatch.setattr(jobs_api.matching_service, "deep_match", lambda *args: {"cached": True})
    assert jobs_api.match_job(job_id, resume_id, object(), owner)["cached"]
    assert [e["event_name"] for e in events] == ["resume_match_started", "resume_match_completed"]
    assert events[-1]["metadata"]["cache_hit"] and events[-1]["latency_ms"] >= 0
    events.clear()
    def failed(*args): raise ValueError("Job needs a meaningful description for Resume Match")
    monkeypatch.setattr(jobs_api.matching_service, "deep_match", failed)
    with pytest.raises(Exception) as exc:
        jobs_api.match_job(job_id, resume_id, object(), owner)
    assert exc.value.status_code == 422
    assert [e["event_name"] for e in events] == ["resume_match_started", "resume_match_failed"]
    assert events[-1]["error_type"] == "insufficient_job_description"
