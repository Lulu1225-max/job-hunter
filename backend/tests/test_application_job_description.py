from types import SimpleNamespace
from uuid import uuid4

from app.api.v1 import applications as applications_api
from app.schemas.applications import ApplicationCreate


class FakeDb:
    def commit(self):
        pass


class CapturingApplicationsRepo:
    def __init__(self):
        self.payload = None
        self.existing = None
        self.create_count = 0

    def get_by_job_id(self, db, user_id, job_id):
        return self.existing

    def create(self, db, user_id, payload):
        self.create_count += 1
        self.payload = payload
        return {"id": str(uuid4()), **payload}


def create_application(monkeypatch, payload, *, linked_job=None, existing=None):
    repo = CapturingApplicationsRepo()
    repo.existing = existing
    monkeypatch.setattr(applications_api, "applications_repo", repo)
    monkeypatch.setattr(applications_api, "ensure_user", lambda db, user_id: None)
    monkeypatch.setattr(
        applications_api.jobs_repo,
        "get_row",
        lambda db, user_id, job_id: linked_job,
    )
    result = applications_api.create_application(
        ApplicationCreate(**payload),
        FakeDb(),
        uuid4(),
    )
    return result, repo.payload


def test_manual_application_with_job_description(monkeypatch):
    result, stored = create_application(
        monkeypatch,
        {"company": "Acme", "job_description": "Own the product roadmap."},
    )

    assert result["job_description"] == "Own the product roadmap."
    assert stored["job_description"] == "Own the product roadmap."


def test_manual_application_without_job_description(monkeypatch):
    result, stored = create_application(monkeypatch, {"company": "Acme"})

    assert result["job_description"] is None
    assert stored["job_description"] is None


def test_job_linked_application_copies_job_description(monkeypatch):
    job_id = uuid4()
    result, stored = create_application(
        monkeypatch,
        {"job_id": str(job_id)},
        linked_job=SimpleNamespace(company="Discovery Co", role="Product Intern", description="Description from Job Discovery"),
    )

    assert result["company"] == "Discovery Co"
    assert result["role"] == "Product Intern"
    assert result["job_description"] == "Description from Job Discovery"
    assert stored["company"] == "Discovery Co"
    assert stored["role"] == "Product Intern"
    assert stored["job_description"] == "Description from Job Discovery"


def test_explicit_application_jd_is_not_overwritten_by_linked_job(monkeypatch):
    job_id = uuid4()
    result, _ = create_application(
        monkeypatch,
        {
            "company": "Acme",
            "job_id": str(job_id),
            "job_description": "Application snapshot",
        },
        linked_job=SimpleNamespace(company="Acme", role="PM", description="Later linked Job description"),
    )

    assert result["job_description"] == "Application snapshot"


def test_duplicate_job_returns_existing_application_without_creating(monkeypatch):
    job_id = uuid4()
    existing = {
        "id": str(uuid4()),
        "job_id": str(job_id),
        "company": "Acme",
        "role": "Engineer",
        "job_description": "Original snapshot",
    }
    result, stored = create_application(
        monkeypatch,
        {"job_id": str(job_id)},
        linked_job=SimpleNamespace(company="Acme", role="Engineer", description="Current JD"),
        existing=existing,
    )

    assert result == existing
    assert stored is None
