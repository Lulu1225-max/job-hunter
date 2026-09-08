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
