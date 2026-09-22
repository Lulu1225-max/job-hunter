from __future__ import annotations

from typing import Any

from app.schemas.question_router import QuestionType, QuestionTypeResult
from app.services.ai.client import ai_client

EXPERIENCE = ("tell me about a time", "describe a time", "give an example", "your resume", "on your resume", "walk me through", "your background", "your project", "your experience", "your strengths", "曾经", "讲一次", "举例", "冲突", "失败经历", "领导力", "简历", "你的背景", "你的项目", "你的经历", "自我介绍", "你做过", "你之前", "项目中", "工作中")
MOTIVATION = ("why this company", "why our company", "why this role", "why do you want", "motivat", "为什么选择", "为什么想", "为什么加入", "求职动机")
CASE = ("case", "estimate", "market size", "design a", "how would you improve", "product sense", "假设", "估算", "市场规模", "设计一个", "如何改进", "产品分析")
KNOWLEDGE = ("what is", "explain", "difference between", "how does", "define", "什么是", "解释", "区别", "原理")


def rule_question_type(question: str, category: str | None = None) -> QuestionType | None:
    text = f"{category or ''} {question}".casefold()
    category_text = (category or "").casefold()
    if any(term in text for term in MOTIVATION) or category_text in {"motivation", "hr motivation"}: return "motivation"
    if any(term in text for term in CASE) or category_text in {"case", "product case", "product analysis"}: return "case"
    if any(term in text for term in EXPERIENCE) or category_text in {"experience", "resume", "resume based", "resume_based", "behavioral", "conflict / collaboration", "actual interview"}: return "experience"
    if any(term in text for term in KNOWLEDGE) or category_text in {"technical", "programming", "database", "backend", "networking", "system design basics", "debugging", "knowledge"}: return "knowledge"
    return None


def classify_question(question: str, category: str | None = None) -> QuestionType:
    ruled = rule_question_type(question, category)
    if ruled: return ruled
    try:
        return ai_client.structured_completion(
            prompt_name="interview_question_classifier", schema=QuestionTypeResult,
            payload={"question": question, "category": category},
            diagnostic_context={"flow": "question_classifier", "question_type": "unknown"},
        ).question_type
    except Exception:
        # The safe fallback does not require or invent personal experience.
        return "knowledge"


def route_summary(question: Any) -> dict[str, Any]:
    question_type = classify_question(question.question, question.category)
    return {"question_type": question_type, "requires_experience": question_type == "experience"}
