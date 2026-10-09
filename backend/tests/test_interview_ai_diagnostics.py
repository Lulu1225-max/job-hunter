import logging

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.api.v1 import interviews
from app.core.config import settings
from app.schemas.question_router import QuestionTypeResult
from app.services.ai import client as module
from app.skills.company_role_research.schemas import (
    RecentSignalItem,
    ReverseQuestionItem,
    ReverseQuestionsSection,
    RoleDecoderItem,
    WhyCompanyRoleItem,
)


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


def test_successful_parse_logs_http_success_without_output(monkeypatch,caplog):
    class SuccessResponses:
        def parse(self,**kwargs):return type("Response",(),{"output_parsed":QuestionTypeResult(question_type="knowledge")})()
    monkeypatch.setattr(settings,"openai_api_key","sk-super-secret")
    monkeypatch.setattr(module,"OpenAI",lambda **kwargs:type("Client",(),{"responses":SuccessResponses()})())
    caplog.set_level(logging.WARNING,logger="uvicorn.error")
    result=module.ai_client.structured_completion(prompt_name="interview_question_classifier",schema=QuestionTypeResult,payload={"question":"PRIVATE QUESTION"},diagnostic_context={"flow":"question_classifier","question_type":"unknown"})
    assert result.question_type=="knowledge"
    assert '"stage":"openai_http_success"' in caplog.text
    assert '"parsed_output_present":true' in caplog.text
    assert "PRIVATE QUESTION" not in caplog.text


def test_missing_parsed_output_has_distinct_safe_stage(monkeypatch,caplog):
    class EmptyResponses:
        def parse(self,**kwargs):return type("Response",(),{"output_parsed":None})()
    monkeypatch.setattr(settings,"openai_api_key","sk-super-secret")
    monkeypatch.setattr(module,"OpenAI",lambda **kwargs:type("Client",(),{"responses":EmptyResponses()})())
    caplog.set_level(logging.WARNING,logger="uvicorn.error")
    with pytest.raises(RuntimeError):module.ai_client.structured_completion(prompt_name="interview_answer",schema=QuestionTypeResult,payload={"answer":"PRIVATE ANSWER"},diagnostic_context={"flow":"interview_answer_generation","question_type":"case"})
    assert '"stage":"output_parsed_missing"' in caplog.text
    assert "PRIVATE ANSWER" not in caplog.text


def test_schema_validation_failure_has_distinct_safe_stage(monkeypatch,caplog):
    class InvalidResponses:
        def parse(self,**kwargs):return QuestionTypeResult.model_validate({"question_type":"not-valid"})
    monkeypatch.setattr(settings,"openai_api_key","sk-super-secret")
    monkeypatch.setattr(module,"OpenAI",lambda **kwargs:type("Client",(),{"responses":InvalidResponses()})())
    caplog.set_level(logging.WARNING,logger="uvicorn.error")
    with pytest.raises(Exception):module.ai_client.structured_completion(prompt_name="interview_question_classifier",schema=QuestionTypeResult,payload={"question":"PRIVATE QUESTION"},diagnostic_context={"flow":"question_classifier","question_type":"unknown"})
    assert '"stage":"schema_validation_failed"' in caplog.text
    assert '"exception_type":"ValidationError"' in caplog.text
    assert "PRIVATE QUESTION" not in caplog.text


def test_schema_validation_diagnostic_logs_only_safe_location_and_constraint(caplog):
    class FocusItem(BaseModel):
        likely_questions: list[str] = Field(min_length=2, max_length=4)

    class ResearchOutput(BaseModel):
        likely_interview_focus: list[FocusItem]

    try:
        ResearchOutput.model_validate({
            "likely_interview_focus": [{"likely_questions": ["PRIVATE MODEL OUTPUT"]}],
        })
    except ValidationError as exc:
        caplog.set_level(logging.WARNING, logger="uvicorn.error")
        module.log_post_openai_stage(
            "schema_validation_failed",
            "company_role_research_generation",
            exc=exc,
            parsed_output_present=False,
        )

    assert '"section":"likely_interview_focus"' in caplog.text
    assert '"field":"likely_questions"' in caplog.text
    assert '"item_index":0' in caplog.text
    assert '"validation_rule":"too_short"' in caplog.text
    assert '"error_type":"ValidationError"' in caplog.text
    assert '"expected_constraint":"min_length=2"' in caplog.text
    assert "PRIVATE MODEL OUTPUT" not in caplog.text


def test_schema_validation_diagnostic_maps_known_why_company_rule_without_text(caplog):
    private_output = (
        "这家公司有清晰的产品和业务场景，我希望了解它如何服务用户。"
        "岗位本身涉及产品规划、需求拆解和跨团队协作，也需要把技术能力落到具体场景。"
        "岗位还要求理解用户需求、梳理产品方案，并和算法及研发团队共同推进实际交付。"
        "对我来说，这个方向很有吸引力，我希望继续深入理解相关产品工作、用户价值和团队目标。"
    )
    with pytest.raises(ValidationError) as raised:
        WhyCompanyRoleItem.model_validate({
            "text": private_output,
            "claim_type": "inference",
            "evidence_ids": ["evidence_company", "evidence_role"],
        })

    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    module.log_post_openai_stage(
        "schema_validation_failed",
        "company_role_research_generation",
        exc=raised.value,
        parsed_output_present=False,
    )

    assert '"field":"text"' in caplog.text
    assert '"validation_rule":"missing_company_reason"' in caplog.text
    assert '"expected_constraint":"company_reason_required"' in caplog.text
    assert private_output not in caplog.text


def test_schema_validation_diagnostic_maps_role_claim_type_without_text(caplog):
    private_output = "PRIVATE ROLE GOAL MODEL OUTPUT"
    with pytest.raises(ValidationError) as raised:
        RoleDecoderItem.model_validate({
            "category": "role_goal",
            "text": private_output,
            "claim_type": "fact",
            "evidence_ids": ["evidence_role"],
        })

    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    module.log_post_openai_stage(
        "schema_validation_failed",
        "company_role_research_generation",
        exc=raised.value,
        parsed_output_present=False,
    )

    assert '"field":"claim_type"' in caplog.text
    assert '"validation_rule":"wrong_claim_type"' in caplog.text
    assert '"expected_constraint":"role_goal_requires_inference"' in caplog.text
    assert private_output not in caplog.text


def test_recent_signal_value_error_maps_to_stable_specific_rule(caplog):
    with pytest.raises(ValidationError) as raised:
        RecentSignalItem.model_validate({
            "title": "PRIVATE RECENT TITLE",
            "why_it_matters_for_interview": "需要关注公司发展",
            "role_relevance": "high",
            "evidence_ids": ["evidence_recent"],
        })

    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    module.log_post_openai_stage(
        "schema_validation_failed",
        "company_role_research_generation",
        exc=raised.value,
        parsed_output_present=True,
    )

    assert '"section":"why_it_matters_for_interview"' not in caplog.text
    assert '"field":"why_it_matters_for_interview"' in caplog.text
    assert '"validation_rule":"vague_interview_relevance"' in caplog.text
    assert '"expected_constraint":"concrete_interview_impact_required"' in caplog.text
    assert "PRIVATE RECENT TITLE" not in caplog.text


@pytest.mark.parametrize(
    ("item", "rule", "field", "constraint"),
    [
        (
            {"question": "如何定义 Agent MVP？", "rationale": "了解团队产品重点和项目目标。", "evidence_ids": ["ev_role"]},
            "methodology_question", "question", "question_must_ask_about_team_reality",
        ),
        (
            {"question": "团队目前最重要的目标", "rationale": "了解团队产品重点和项目目标。", "evidence_ids": ["ev_role"]},
            "not_a_question", "question", "question_mark_required",
        ),
        (
            {"question": "团队目前最重要的目标是什么？", "rationale": "有助于了解公司", "evidence_ids": ["ev_role"]},
            "vague_rationale", "rationale", "specific_information_gain_required",
        ),
        (
            {"question": "这个岗位如何判断我的经历是否合适？", "rationale": "了解团队对候选人经历的预期。", "evidence_ids": ["ev_role"]},
            "candidate_fit_material", "question_or_rationale", "no_candidate_fit",
        ),
    ],
)
def test_reverse_question_diagnostics_have_stable_safe_rules(caplog, item, rule, field, constraint):
    with pytest.raises(ValidationError) as raised:
        ReverseQuestionItem.model_validate(item)
    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    module.log_post_openai_stage(
        "schema_validation_failed",
        "company_role_research_generation",
        exc=raised.value,
        parsed_output_present=False,
    )
    assert f'"validation_rule":"{rule}"' in caplog.text
    assert f'"field":"{field}"' in caplog.text
    assert f'"expected_constraint":"{constraint}"' in caplog.text
    assert item["question"] not in caplog.text and item["rationale"] not in caplog.text


def test_reverse_question_duplicate_diagnostic_is_safe_and_stable(caplog):
    item = ReverseQuestionItem(
        question="团队目前最重要的产品目标是什么？",
        rationale="了解团队当前产品重点和岗位目标。",
        evidence_ids=["ev_role"],
    )
    with pytest.raises(ValidationError) as raised:
        ReverseQuestionsSection(status="available", items=[item, item])
    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    module.log_post_openai_stage(
        "schema_validation_failed",
        "company_role_research_generation",
        exc=raised.value,
        parsed_output_present=False,
    )
    assert '"validation_rule":"duplicate_question"' in caplog.text
    assert '"field":"question"' in caplog.text
    assert '"expected_constraint":"unique_questions_required"' in caplog.text
    assert item.question not in caplog.text and item.rationale not in caplog.text


def test_non_sdk_parse_failure_has_distinct_safe_stage(monkeypatch,caplog):
    class BrokenResponses:
        def parse(self,**kwargs):raise TypeError("PRIVATE RESPONSE BODY")
    monkeypatch.setattr(settings,"openai_api_key","sk-super-secret")
    monkeypatch.setattr(module,"OpenAI",lambda **kwargs:type("Client",(),{"responses":BrokenResponses()})())
    caplog.set_level(logging.WARNING,logger="uvicorn.error")
    with pytest.raises(TypeError):module.ai_client.structured_completion(prompt_name="interview_answer",schema=QuestionTypeResult,payload={"answer":"PRIVATE ANSWER"},diagnostic_context={"flow":"interview_answer_generation","question_type":"knowledge"})
    assert '"stage":"structured_parse_failed"' in caplog.text
    assert "PRIVATE RESPONSE BODY" not in caplog.text and "PRIVATE ANSWER" not in caplog.text
