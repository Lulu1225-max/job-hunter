from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


MAX_SEARCH_ROUNDS = 3
MAX_FETCH_PAGES = 6
MAX_FETCH_PER_ROUND = 3

CoverageStatus = Literal["sufficient", "weak", "missing"]

KNOWLEDGE_DIMENSIONS = (
    "company_overview",
    "core_business",
    "brands_products",
    "platforms_ecosystem",
    "strategic_business",
    "customer_market",
    "role_relevant_context",
    "comparable_context",
)


@dataclass(frozen=True)
class ResearchPlan:
    missing_dimensions: list[str]
    search_needed: bool
    search_query: str
    preferred_source_types: list[str]
    reason: str


_DIMENSION_MARKERS: dict[str, tuple[str, ...]] = {
    "company_overview": (
        "company", "corporation", "公司", "集团", "成立", "总部", "about", "overview",
    ),
    "core_business": (
        "business", "业务", "主营", "产品", "product", "service", "服务", "segment",
    ),
    "brands_products": (
        "brand", "品牌", "product", "产品", "smartphone", "汽车", "设备", "device",
    ),
    "platforms_ecosystem": (
        "platform", "ecosystem", "operating system", "os", "平台", "生态", "操作系统",
        "developer", "开发者", "iot", "aiot",
    ),
    "strategic_business": (
        "strategy", "strategic", "重点业务", "战略", "布局", "投资", "automotive", "汽车",
    ),
    "customer_market": (
        "customer", "consumer", "user", "market", "客户", "消费者", "用户", "市场",
    ),
    "comparable_context": (
        "alternative", "comparison", "competitor", "可比", "对比", "竞品", "同类产品",
    ),
}


def assess_profile_coverage(
    evidence: list[dict[str, str]],
    *,
    job_title: str | None,
    saved_jd: str | None,
) -> dict[str, CoverageStatus]:
    """Cheap deterministic coverage assessment; it never invents company facts."""
    texts = [str(item.get("text") or "").casefold() for item in evidence]
    categories = [str(item.get("source_category") or "") for item in evidence]
    coverage: dict[str, CoverageStatus] = {}
    for dimension, markers in _DIMENSION_MARKERS.items():
        matches = sum(any(marker in text for marker in markers) for text in texts)
        coverage[dimension] = "sufficient" if matches >= 2 else "weak" if matches == 1 else "missing"

    category_dimensions = {
        "overview": "company_overview",
        "investor": "core_business",
        "platform_ecosystem": "platforms_ecosystem",
        "strategic_product": "brands_products",
    }
    for category, dimension in category_dimensions.items():
        count = categories.count(category)
        # A successfully fetched page whose category is explicit is enough for
        # basic coverage; text-marker counts still distinguish richer coverage.
        if count >= 1:
            coverage[dimension] = "sufficient"

    role_context = " ".join(filter(None, (job_title, saved_jd))).casefold()
    role_terms = _role_terms(role_context)
    role_matches = sum(
        any(any(token.casefold() in text for token in term.split()) for term in role_terms)
        for text in texts
    ) if role_terms else 0
    if role_matches >= 2:
        coverage["role_relevant_context"] = "sufficient"
    elif role_matches == 1:
        coverage["role_relevant_context"] = "weak"
    else:
        coverage["role_relevant_context"] = "missing"
    return {dimension: coverage.get(dimension, "missing") for dimension in KNOWLEDGE_DIMENSIONS}


def plan_profile_search(
    company_name: str,
    *,
    job_title: str | None,
    saved_jd: str | None,
    coverage: dict[str, CoverageStatus],
) -> ResearchPlan:
    missing = [key for key in KNOWLEDGE_DIMENSIONS if coverage.get(key) != "sufficient"]
    core_missing = [key for key in ("company_overview", "core_business", "brands_products") if coverage.get(key) != "sufficient"]
    role_context = " ".join(filter(None, (job_title, saved_jd))).casefold()
    role_terms = _role_terms(role_context)

    if coverage.get("company_overview") != "sufficient":
        query = f'{company_name} 官方 关于我们 公司简介 核心业务 产品生态 投资者关系 年报'
        preferred = ["official_company", "investor_relations", "official_product"]
        reason = "complete_core_company_profile"
    elif core_missing:
        terms = _query_role_terms(role_terms)
        query = f'{company_name} 官方 核心业务 产品 平台 生态 操作系统 {terms}'
        preferred = ["official_product", "official_platform", "investor_relations"]
        reason = "complete_business_products_and_role_context"
    elif coverage.get("platforms_ecosystem") != "sufficient" or coverage.get("role_relevant_context") != "sufficient":
        terms = _query_role_terms(role_terms)
        query = f'{company_name} 官方 平台 生态 操作系统 产品 {terms} official ecosystem'
        preferred = ["official_platform", "official_product", "developer_docs"]
        reason = "complete_platform_and_role_context"
    elif coverage.get("strategic_business") != "sufficient":
        query = f'{company_name} 官方 重点业务 战略产品 生态 投资者关系 official strategic business'
        preferred = ["official_product", "investor_relations", "official_newsroom"]
        reason = "complete_strategic_business"
    elif coverage.get("customer_market") == "missing":
        query = f'{company_name} 官方 用户 客户 市场 业务概览 official customers market'
        preferred = ["official_company", "investor_relations"]
        reason = "complete_customer_market"
    else:
        return ResearchPlan(missing, False, "", [], "coverage_sufficient")

    return ResearchPlan(missing, True, query.strip(), preferred, reason)


def core_coverage_sufficient(coverage: dict[str, CoverageStatus]) -> bool:
    return all(coverage.get(key) == "sufficient" for key in (
        "company_overview", "core_business", "brands_products",
    ))


def extended_coverage_sufficient(
    coverage: dict[str, CoverageStatus],
    *,
    has_role_context: bool,
) -> bool:
    if not core_coverage_sufficient(coverage):
        return False
    if not has_role_context:
        return True
    return (
        coverage.get("role_relevant_context") == "sufficient"
        and coverage.get("platforms_ecosystem") != "missing"
    )


def _role_terms(text: str) -> list[str]:
    groups = (
        ("AI 人工智能", ("ai", "人工智能", "大模型", "llm")),
        ("Agent 智能体", ("agent", "智能体")),
        ("AI助手", ("assistant", "助手")),
        ("工作流", ("workflow", "工作流", "流程自动化")),
        ("知识管理", ("knowledge", "知识管理")),
        ("跨设备", ("cross-device", "跨设备", "多终端")),
        ("电商增长", ("电商", "commerce", "增长", "转化")),
    )
    return [label for label, markers in groups if any(marker in text for marker in markers)]


def _query_role_terms(role_terms: list[str]) -> str:
    if not role_terms:
        return "操作系统 物联网"
    selected = list(role_terms[:2])
    if any("AI" in term or "Agent" in term for term in selected):
        selected.extend(["AI助手", "跨设备"])
    return " ".join(dict.fromkeys(selected))
