import logging

import pytest
from fastapi import HTTPException

from app.api.v1 import interviews
from app.core.config import settings
from app.schemas.question_router import QuestionTypeResult
from app.services.ai import client as module


class FakeOpenAIError(Exception):
    def __init__(self, status_code):
        super().__init__("sk-super-secret Bearer access-token FULL PROMPT PRIVATE RESUME PRIVATE JD PRIVATE ANSWER")
        self.status_code = status_code
        self.code = "rate_limit_exceeded" if status_code == 429 else None
        self.type = "invalid_request_error" if status_code == 400 else "api_error"
        self.body = {"error": {"code": self.code, "type": self.type,
                               "message": "FULL PROMPT PRIVATE RESUME PRIVATE JD PRIVATE ANSWER sk-super-secret"}}


class Responses:
    def __init__(self, error): self.error=error
    def parse(self, **kwargs): raise self.error


class FakeClient:
    def __init__(self, error): self.responses=Responses(error)


@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
def test_openai_http_failures_log_only_safe_structured_fields(monkeypatch, caplog, status):
    error=FakeOpenAIError(status)
    monkeypatch.setattr(settings,"openai_api_key","sk-super-secret")
    monkeypatch.setattr(module,"OpenAI",lambda **kwargs:FakeClient(error))
    caplog.set_level(logging.ERROR,logger="uvicorn.error")
    with pytest.raises(FakeOpenAIError):
        module.ai_client.structured_completion(
            prompt_name="interview_question_classifier", schema=QuestionTypeResult,
            payload={"question":"FULL QUESTION","resume":"PRIVATE RESUME","job":"PRIVATE JD","answer":"PRIVATE ANSWER"},
            diagnostic_context={"flow":"question_classifier","question_type":"unknown"},
        )
    log=caplog.text
    assert '"exception_type":"FakeOpenAIError"' in log
    assert f'"status_code":{status}' in log
    assert '"openai_error_type":' in log and '"safe_message":' in log
    assert '"flow":"question_classifier"' in log and '"question_type":"unknown"' in log
    for secret in ("sk-super-secret","Bearer","access-token","FULL PROMPT","FULL QUESTION","PRIVATE RESUME","PRIVATE JD","PRIVATE ANSWER"):
        assert secret not in log


def test_answer_flow_includes_question_type_without_payload(monkeypatch, caplog):
    error=FakeOpenAIError(429)
    monkeypatch.setattr(settings,"openai_api_key","sk-super-secret")
    monkeypatch.setattr(module,"OpenAI",lambda **kwargs:FakeClient(error))
    caplog.set_level(logging.ERROR,logger="uvicorn.error")
    with pytest.raises(FakeOpenAIError):
        module.ai_client.structured_completion(
            prompt_name="interview_answer", schema=QuestionTypeResult,
            payload={"resume":"PRIVATE RESUME","job":"PRIVATE JD"},
            diagnostic_context={"flow":"interview_answer_generation","question_type":"motivation"},
        )
    assert '"flow":"interview_answer_generation"' in caplog.text
    assert '"question_type":"motivation"' in caplog.text
    assert "PRIVATE RESUME" not in caplog.text and "PRIVATE JD" not in caplog.text


def test_interview_api_still_returns_generic_503():
    with pytest.raises(HTTPException) as raised:
        interviews.fail(FakeOpenAIError(401))
    assert raised.value.status_code == 503
    assert raised.value.detail == {"error": {"code": "AI_UNAVAILABLE", "message": "Interview AI is temporarily unavailable"}}
    assert "sk-super-secret" not in str(raised.value.detail)
