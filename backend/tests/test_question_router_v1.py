from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.question_router import QuestionTypeResult
from app.services import interview_service as interview_module
from app.services import question_router as router_module


def test_explainable_rules_cover_all_question_types():
    assert router_module.classify_question("Tell me about a time you resolved conflict", "behavioral") == "behavioral"
    assert router_module.classify_question("What is a database index?", "technical") == "knowledge"
    assert router_module.classify_question("Why do you want this role?", "motivation") == "motivation"
    assert router_module.classify_question("Walk me through your resume", "resume") == "resume_based"
    assert router_module.classify_question("Estimate the market size for this product", "case") == "case"


def test_ambiguous_question_uses_constrained_llm_classifier(monkeypatch):
    captured=[]
    monkeypatch.setattr(router_module.ai_client,"structured_completion",lambda **kw:(captured.append(kw) or QuestionTypeResult(question_type="case")))
    assert router_module.classify_question("How would you approach this?", "other") == "case"
    assert captured[0]["schema"] is QuestionTypeResult


def test_classifier_failure_falls_back_without_forcing_experience(monkeypatch):
    monkeypatch.setattr(router_module.ai_client,"structured_completion",lambda **kw:(_ for _ in ()).throw(RuntimeError("offline")))
    assert router_module.classify_question("An ambiguous interview prompt", "other") == "knowledge"


def test_non_behavioral_retrieval_is_blocked(monkeypatch):
    question=SimpleNamespace(id=uuid4(),question="What is product-market fit?",category="knowledge",application_id=None)
    monkeypatch.setattr(interview_module.interview_questions_repo,"get",lambda *args:question)
    monkeypatch.setattr(interview_module.experience_service,"retrieve",lambda *args:pytest.fail("knowledge queried Experience Library"))
    with pytest.raises(ValueError,match="only available for behavioral"):
        interview_module.interview_service.retrieve(object(),uuid4(),question.id,3)


def test_behavioral_question_uses_experience_retrieval(monkeypatch):
    owner=uuid4();question=SimpleNamespace(id=uuid4(),question="Tell me about a time you led a team",category="behavioral",application_id=None,company="Acme",role="PM")
    calls=[]
    monkeypatch.setattr(interview_module.interview_questions_repo,"get",lambda *args:question)
    monkeypatch.setattr(interview_module.experience_service,"retrieve",lambda *args:(calls.append(args) or {"recommendations":[]}))
    interview_module.interview_service.retrieve(object(),owner,question.id,3)
    assert calls and calls[0][1]==owner and calls[0][-1]==3


def test_motivation_context_uses_job_profile_and_resume(monkeypatch):
    owner=uuid4();question=SimpleNamespace(application_id=uuid4(),company="Acme",role="PM")
    resume=SimpleNamespace(extracted_text="Built a real product")
    monkeypatch.setattr(interview_module.interview_service,"_context",lambda *args:{"text":"Job Description: AI product role"})
    monkeypatch.setattr(interview_module.profile_repo,"get",lambda *args:{"target_roles":["PM"]})
    monkeypatch.setattr(interview_module.resumes_repo,"default",lambda *args:{"id":str(uuid4())})
    monkeypatch.setattr(interview_module.resumes_repo,"get",lambda *args:resume)
    text=interview_module.interview_service._answer_context(object(),owner,question,"motivation")
    assert "Job Description" in text and "target_roles" in text and "Built a real product" in text


def test_resume_based_context_uses_resume_and_profile_without_job(monkeypatch):
    owner=uuid4();question=SimpleNamespace(application_id=None,company=None,role=None)
    monkeypatch.setattr(interview_module.interview_service,"_context",lambda *args:{"text":"unused job"})
    monkeypatch.setattr(interview_module.profile_repo,"get",lambda *args:{"major":"Computer Science"})
    monkeypatch.setattr(interview_module.resumes_repo,"default",lambda *args:{"id":str(uuid4())})
    monkeypatch.setattr(interview_module.resumes_repo,"get",lambda *args:SimpleNamespace(extracted_text="Resume evidence"))
    text=interview_module.interview_service._answer_context(object(),owner,question,"resume_based")
    assert "Computer Science" in text and "Resume evidence" in text and "unused job" not in text


def test_case_route_does_not_require_experience():
    question=SimpleNamespace(question="Design a product for students",category="case")
    assert router_module.route_summary(question)=={"question_type":"case","requires_experience":False}
