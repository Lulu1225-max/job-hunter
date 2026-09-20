from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.v1 import debug
from app.core.config import settings
from app.core.security import get_current_user_id
from app.main import app
from app.services.ai import client as client_module


class FakeResponse:
    output_text = "SECRET GENERATED CONTENT"


class Responses:
    def __init__(self): self.calls=[]
    def create(self, **kwargs): self.calls.append(kwargs);return FakeResponse()


class FakeOpenAI:
    responses=Responses()


class FakeOpenAIError(Exception):
    status_code=429
    code="rate_limit_exceeded"
    type="rate_limit_error"
    body={"error":{"message":"sk-secret PRIVATE PROMPT PRIVATE USER DATA"}}


def test_connectivity_client_uses_configured_model_and_minimal_input(monkeypatch):
    fake=FakeOpenAI();monkeypatch.setattr(settings,"openai_api_key","sk-secret");monkeypatch.setattr(settings,"openai_model","gpt-test")
    monkeypatch.setattr(client_module,"OpenAI",lambda **kwargs:fake)
    client_module.ai_client.check_responses_api()
    assert fake.responses.calls==[{"model":"gpt-test","input":"Reply with OK only.","max_output_tokens":5}]


def test_debug_endpoint_requires_existing_jwt_auth():
    response=TestClient(app).get("/api/v1/debug/openai")
    assert response.status_code==401


def test_debug_success_returns_only_ok_and_model(monkeypatch):
    app.dependency_overrides[get_current_user_id]=lambda:uuid4()
    monkeypatch.setattr(debug.ai_client,"check_responses_api",lambda:None)
    monkeypatch.setattr(settings,"openai_model","gpt-4.1-mini")
    try: response=TestClient(app).get("/api/v1/debug/openai")
    finally: app.dependency_overrides.clear()
    assert response.status_code==200
    assert response.json()=={"ok":True,"model":"gpt-4.1-mini"}


def test_debug_failure_returns_safe_fields_only(monkeypatch):
    app.dependency_overrides[get_current_user_id]=lambda:uuid4()
    def fail(): raise FakeOpenAIError("sk-secret PRIVATE PROMPT PRIVATE USER DATA")
    monkeypatch.setattr(debug.ai_client,"check_responses_api",fail)
    try: response=TestClient(app).get("/api/v1/debug/openai")
    finally: app.dependency_overrides.clear()
    assert response.status_code==503
    assert response.json()=={
        "ok":False,"exception_type":"FakeOpenAIError","status_code":429,
        "openai_error_code":"rate_limit_exceeded","openai_error_type":"rate_limit_error",
        "safe_message":"OpenAI rate limit exceeded",
    }
    rendered=response.text
    for private in ("sk-secret","PRIVATE PROMPT","PRIVATE USER DATA","Reply with OK only","token","Authorization"):
        assert private not in rendered
