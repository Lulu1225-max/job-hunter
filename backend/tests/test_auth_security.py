from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.v1 import applications as applications_api
from app.core import security
from app.core.config import settings
from app.core.database import get_db
from app.main import app


TEST_SECRET = "test-supabase-jwt-secret-at-least-32-bytes"
FORGED_SECRET = "forged-supabase-jwt-secret-at-least-32-bytes"
TEST_ISSUER = "https://unit-test.supabase.co/auth/v1"


def signed_token(
    user_id: UUID,
    email: str,
    *,
    expires_at: datetime | None = None,
    secret: str = TEST_SECRET,
) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "aud": "authenticated",
            "iss": TEST_ISSUER,
            "role": "authenticated",
            "exp": expires_at or datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        secret,
        algorithm="HS256",
    )


class FakeApplicationsRepo:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def list(self, db, user_id, status=None, limit=None, sort="created_at_desc"):
        return [record for record in self.records.values() if record["user_id"] == str(user_id)]

    def create(self, db, user_id, payload):
        assert payload.get("user_id") is None
        record = {"id": str(uuid4()), "user_id": str(user_id), **payload}
        self.records[record["id"]] = record
        return record

    def get(self, db, user_id, application_id):
        record = self.records.get(str(application_id))
        if not record or record["user_id"] != str(user_id):
            return None
        return record

    def update_status(self, db, user_id, application_id, status):
        record = self.get(db, user_id, application_id)
        if not record:
            return None
        from app.utils.normalization import canonical_status
        record["status"] = canonical_status(status)
        return record


class FakeDb:
    def commit(self) -> None:
        return None


@pytest.fixture
def auth_client(monkeypatch):
    fake_repo = FakeApplicationsRepo()

    monkeypatch.setattr(settings, "supabase_url", "https://unit-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_publishable_key", "test-publishable-key")
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    monkeypatch.setattr(applications_api, "applications_repo", fake_repo)
    monkeypatch.setattr(applications_api, "ensure_user", lambda db, user_id: None)
    monkeypatch.setattr(
        security,
        "_decode_with_jwks",
        lambda token: (_ for _ in ()).throw(security.AuthError("No JWKS in unit test")),
    )
    monkeypatch.setattr(
        security,
        "_verify_with_auth_server",
        lambda token: (_ for _ in ()).throw(security.AuthError("No auth server in unit test")),
    )

    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_authenticated_user_b_cannot_access_user_a_application(auth_client):
    user_a = uuid4()
    user_b = uuid4()

    created = auth_client.post(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {signed_token(user_a, 'a@example.com')}"},
        json={
            "company": "Private Company A",
            "role": "Private Role",
            "status": "saved",
            "user_id": str(user_b),
        },
    )
    assert created.status_code == 200
    application_id = created.json()["id"]
    assert created.json()["user_id"] == str(user_a)

    visible_to_owner = auth_client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {signed_token(user_a, 'a@example.com')}"},
    )
    assert visible_to_owner.status_code == 200
    assert len(visible_to_owner.json()) == 1
    assert visible_to_owner.json()[0]["id"] == application_id

    hidden_from_other_user = auth_client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {signed_token(user_b, 'b@example.com')}"},
    )
    assert hidden_from_other_user.status_code == 200
    assert hidden_from_other_user.json() == []

    blocked = auth_client.get(
        f"/api/v1/applications/{application_id}",
        headers={"Authorization": f"Bearer {signed_token(user_b, 'b@example.com')}"},
    )
    assert blocked.status_code == 404


def test_final_interview_status_round_trips_through_api(auth_client):
    user_id = uuid4()
    headers = {"Authorization": f"Bearer {signed_token(user_id, 'status@example.com')}"}
    created = auth_client.post(
        "/api/v1/applications",
        headers=headers,
        json={"company": "Status Co", "role": "Candidate", "status": "saved"},
    )

    updated = auth_client.patch(
        f"/api/v1/applications/{created.json()['id']}/status?status=final_interview",
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "final_interview"


def test_forged_token_is_rejected(auth_client):
    forged_token = signed_token(uuid4(), "attacker@example.com", secret=FORGED_SECRET)

    response = auth_client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {forged_token}"},
    )

    assert response.status_code == 401


def test_expired_token_is_rejected(auth_client):
    expired_token = signed_token(
        uuid4(),
        "expired@example.com",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    response = auth_client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401

from app.api.v1 import jobs as jobs_api

class FakeJobService:
    def __init__(self): self.records={}
    def create_job(self,db,user_id,payload):
        row={"id":str(uuid4()),"user_id":str(user_id),**payload};self.records[row["id"]]=row;return row
    def list_jobs(self,db,user_id,filters): return [r for r in self.records.values() if r["user_id"]==str(user_id)]
    def page_jobs(self,db,user_id,filters,page,page_size):
        rows=self.list_jobs(db,user_id,filters);query=(filters.get("q") or filters.get("keyword") or "").casefold()
        if query:rows=[row for row in rows if query in " ".join(str(row.get(key) or "") for key in ("company","role","location","industry","graduation_cohort")).casefold()]
        if filters.get("sort")=="deadline":rows.sort(key=lambda row:row.get("deadline") or "9999-12-31")
        start=(page-1)*page_size;return rows[start:start+page_size],len(rows)
    def get_job(self,db,user_id,job_id):
        row=self.records.get(str(job_id));return row if row and row["user_id"]==str(user_id) else None
    def update_job(self,db,user_id,job_id,payload):
        row=self.get_job(db,user_id,job_id)
        if row:row.update(payload)
        return row
    def delete_job(self,db,user_id,job_id):
        row=self.get_job(db,user_id,job_id)
        if not row:return False
        del self.records[str(job_id)];return True

def test_job_crud_and_cross_user_isolation_through_real_auth(auth_client,monkeypatch):
    service=FakeJobService();monkeypatch.setattr(jobs_api,"job_service",service);monkeypatch.setattr(jobs_api,"ensure_user",lambda db,user_id:None)
    monkeypatch.setattr(jobs_api.profile_repo,"get",lambda db,user_id:None);monkeypatch.setattr(jobs_api.resumes_repo,"default",lambda db,user_id:None)
    a,b=uuid4(),uuid4();ah={"Authorization":f"Bearer {signed_token(a,'a@example.com')}"};bh={"Authorization":f"Bearer {signed_token(b,'b@example.com')}"}
    created=auth_client.post("/api/v1/jobs",headers=ah,json={"company":"Acme","role":"Engineer","application_start_date":"2027-01-01","campus_category":"秋招","referral_available":True,"graduation_cohort":"2027届","company_type":"民营"});assert created.status_code==200;job_id=created.json()["id"]
    assert created.json()["referral_available"] is True and created.json()["graduation_cohort"]=="2027届"
    assert auth_client.get("/api/v1/jobs",headers=ah).json()["items"][0]["id"]==job_id
    assert auth_client.get(f"/api/v1/jobs/{job_id}",headers=bh).status_code==404
    assert auth_client.patch(f"/api/v1/jobs/{job_id}",headers=bh,json={"role":"Thief"}).status_code==404
    assert auth_client.delete(f"/api/v1/jobs/{job_id}",headers=bh).status_code==404
    updated=auth_client.patch(f"/api/v1/jobs/{job_id}",headers=ah,json={"role":"Senior Engineer","referral_available":False,"company_type":"国企"});assert updated.status_code==200 and updated.json()["role"]=="Senior Engineer" and updated.json()["referral_available"] is False and updated.json()["company_type"]=="国企"
    assert auth_client.delete(f"/api/v1/jobs/{job_id}",headers=ah).status_code==204
    assert auth_client.get(f"/api/v1/jobs/{job_id}",headers=ah).status_code==404


def test_job_list_preloads_readiness_context_once(auth_client, monkeypatch):
    owner = uuid4()
    service = FakeJobService()
    for index in range(30):
        row = {
            "id": str(uuid4()), "user_id": str(owner), "company": f"Company {index}",
            "role": None,
            "description": "Short company recruitment record" if index else "We are hiring candidates to build Python services, analyze product data, collaborate with users, improve reliable systems, and deliver production software.",
            "location": "Beijing", "job_type": "Internship", "campus_category": None,
            "graduation_cohort": "2027", "education_requirements": [], "required_skills": [],
            "technical_skills": [], "product_skills": [], "soft_skills": [],
        }
        service.records[row["id"]] = row
    calls = {"profile": 0, "default": 0}
    monkeypatch.setattr(jobs_api, "job_service", service)
    monkeypatch.setattr(jobs_api, "ensure_user", lambda db, user_id: None)
    monkeypatch.setattr(jobs_api.profile_repo, "get", lambda db, user_id: calls.__setitem__("profile", calls["profile"] + 1) or {})
    monkeypatch.setattr(jobs_api.resumes_repo, "default", lambda db, user_id: calls.__setitem__("default", calls["default"] + 1) or {"id": str(uuid4())})
    monkeypatch.setattr("app.repositories.database.jobs_repo.get_row", lambda *args: pytest.fail("list rendering refetched a job"))
    monkeypatch.setattr("app.services.matching.ai_client.get_embedding", lambda *args: pytest.fail("list rendering called OpenAI"))
    headers = {"Authorization": f"Bearer {signed_token(owner, 'owner@example.com')}"}

    response = auth_client.get("/api/v1/jobs?sort=recommended", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 20
    assert response.json()["total"] == 30 and response.json()["total_pages"] == 2
    assert calls == {"profile": 1, "default": 1}
    assert response.json()["items"][0]["match"]["status"] == "ready"
    assert all(item["match"]["status"] == "limited_data" for item in response.json()["items"][1:])


def test_job_pagination_search_sort_and_user_scope(auth_client,monkeypatch):
    owner,other=uuid4(),uuid4();service=FakeJobService()
    records=[
        {"company":"字节跳动","role":"AI产品经理","location":"北京","industry":"科技","graduation_cohort":"2027届","deadline":"2027-03-01"},
        {"company":"贵州融担","role":None,"location":"贵阳","industry":"金融","graduation_cohort":"2026届","deadline":"2027-01-01"},
        {"company":"Other","role":"Engineer","location":"Sydney","industry":"Tech","graduation_cohort":"2027","deadline":"2027-02-01"},
    ]
    for index,payload in enumerate(records):
        user=other if index==2 else owner;row={"id":str(uuid4()),"user_id":str(user),"description":"Short record","job_type":None,"campus_category":None,"education_requirements":[],"required_skills":[],"technical_skills":[],"product_skills":[],"soft_skills":[],**payload};service.records[row["id"]]=row
    monkeypatch.setattr(jobs_api,"job_service",service);monkeypatch.setattr(jobs_api,"ensure_user",lambda *args:None)
    monkeypatch.setattr(jobs_api.profile_repo,"get",lambda *args:{});monkeypatch.setattr(jobs_api.resumes_repo,"default",lambda *args:None)
    headers={"Authorization":f"Bearer {signed_token(owner,'owner@example.com')}"}
    first=auth_client.get("/api/v1/jobs?page=1&page_size=1&sort=deadline",headers=headers).json()
    second=auth_client.get("/api/v1/jobs?page=2&page_size=1&sort=deadline",headers=headers).json()
    beyond=auth_client.get("/api/v1/jobs?page=3&page_size=1",headers=headers).json()
    searched=auth_client.get("/api/v1/jobs?q=2027&page=1&page_size=20",headers=headers).json()
    assert first["items"][0]["company"]=="贵州融担" and first["total"]==2 and first["total_pages"]==2
    assert second["items"][0]["company"]=="字节跳动" and second["page"]==2
    assert beyond["items"]==[] and beyond["total"]==2
    assert searched["total"]==1 and searched["items"][0]["role"]=="AI产品经理"


def test_job_preview_route_accepts_frontend_payload_shape(auth_client, monkeypatch):
    user_id = uuid4()
    captured = {}

    def preview_rows(db, authenticated_user_id, preview_id, options):
        captured.update(options)
        assert authenticated_user_id == user_id
        return {"total_rows": 1, "invalid": 0, "skipped_blank": 0, "issues": [], "warnings": [], "sample_rows": []}

    monkeypatch.setattr(jobs_api.job_service, "preview_rows", preview_rows)
    monkeypatch.setattr(jobs_api, "ensure_user", lambda db, current_user_id: None)
    payload = {
        "sheet_name": "名企直推",
        "header_row": 2,
        "mapping": {
            "公司名称": "company",
            "岗位名称": "role",
            "备注": None,
        },
    }
    response = auth_client.post(
        f"/api/v1/jobs/import/preview/{uuid4()}",
        headers={"Authorization": f"Bearer {signed_token(user_id, 'a@example.com')}"},
        json=payload,
    )
    assert response.status_code == 200
    assert captured == payload


def test_manual_job_create_without_role(auth_client, monkeypatch):
    service = FakeJobService()
    monkeypatch.setattr(jobs_api, "job_service", service)
    monkeypatch.setattr(jobs_api, "ensure_user", lambda db, current_user_id: None)
    user_id = uuid4()
    response = auth_client.post(
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {signed_token(user_id, 'a@example.com')}"},
        json={"company": "Company-level campus recruitment"},
    )
    assert response.status_code == 200
    assert response.json()["company"] == "Company-level campus recruitment"
    assert response.json().get("role") is None
