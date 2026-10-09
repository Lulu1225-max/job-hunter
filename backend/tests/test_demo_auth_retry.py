from uuid import uuid4

import httpx
import pytest

from app.core import security
from app.core.config import settings
from app.api.v1 import auth as auth_api
from fastapi import HTTPException


def session_payload():
    return {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "user": {"id": str(uuid4()), "email": "demo@example.com"},
    }


def install_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        security,
        "_supabase_auth_client",
        lambda: httpx.Client(transport=transport, follow_redirects=False, trust_env=False),
    )
    monkeypatch.setattr(settings, "supabase_url", "https://unit-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_publishable_key", "test-publishable-key")


@pytest.mark.parametrize(
    "network_error",
    [
        lambda request: httpx.ConnectError("SSL EOF", request=request),
        lambda request: httpx.ReadError("connection reset", request=request),
        lambda request: httpx.ReadTimeout("read timed out", request=request),
        lambda request: httpx.RemoteProtocolError("server disconnected", request=request),
    ],
)
def test_password_auth_retries_network_errors_with_fresh_attempts(monkeypatch, caplog, network_error):
    attempts = []
    sleeps = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 3:
            raise network_error(request)
        return httpx.Response(200, json=session_payload())

    install_client(monkeypatch, handler)
    monkeypatch.setattr(security.time, "sleep", sleeps.append)

    result = security.authenticate_supabase_password("demo@example.com", "private-password")

    assert result["user"]["email"] == "demo@example.com"
    assert len(attempts) == 3
    assert sleeps == [0.2, 0.4]
    assert '"auth_stage":"supabase_password_auth"' in caplog.text
    assert '"endpoint_type":"token_password_grant"' in caplog.text
    assert "private-password" not in caplog.text
    assert "test-publishable-key" not in caplog.text
    assert "demo@example.com" not in caplog.text


def test_password_auth_does_not_retry_http_auth_errors(monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(401, json={"error": "invalid credentials"})

    install_client(monkeypatch, handler)

    with pytest.raises(security.AuthError, match="password authentication failed"):
        security.authenticate_supabase_password("demo@example.com", "wrong-password")

    assert len(attempts) == 1


def test_password_auth_stops_after_bounded_network_retries(monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(request)
        raise httpx.ConnectError("SSL EOF", request=request)

    install_client(monkeypatch, handler)
    monkeypatch.setattr(security.time, "sleep", lambda delay: None)

    with pytest.raises(security.AuthNetworkError):
        security.authenticate_supabase_password("demo@example.com", "private-password")

    assert len(attempts) == security.SUPABASE_AUTH_MAX_ATTEMPTS


def test_demo_endpoint_distinguishes_network_unavailability(monkeypatch):
    monkeypatch.setattr(settings, "demo_user_email", "demo@example.com")
    monkeypatch.setattr(settings, "demo_user_password", "private-password")
    monkeypatch.setattr(
        auth_api,
        "authenticate_supabase_password",
        lambda email, password: (_ for _ in ()).throw(security.AuthNetworkError("temporary network failure")),
    )

    with pytest.raises(HTTPException) as exc:
        auth_api.demo_login(object())

    assert exc.value.status_code == 503
    assert exc.value.detail["error"]["code"] == "DEMO_AUTH_UNAVAILABLE"


def test_demo_endpoint_keeps_non_retryable_auth_failure(monkeypatch):
    monkeypatch.setattr(settings, "demo_user_email", "demo@example.com")
    monkeypatch.setattr(settings, "demo_user_password", "private-password")
    monkeypatch.setattr(
        auth_api,
        "authenticate_supabase_password",
        lambda email, password: (_ for _ in ()).throw(security.AuthError("invalid credentials")),
    )

    with pytest.raises(HTTPException) as exc:
        auth_api.demo_login(object())

    assert exc.value.status_code == 502
    assert exc.value.detail["error"]["code"] == "DEMO_AUTH_FAILED"
