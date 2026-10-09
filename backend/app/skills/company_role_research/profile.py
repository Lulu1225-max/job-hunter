from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.ai.client import ai_client


COMPANY_PROFILE_TTL_DAYS = 30
COMPANY_PROFILE_GENERATION_VERSION = "company-profile-v1"


class ComparableProductDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_name: str = Field(min_length=1, max_length=200)
    reference_type: Literal["competitor_reference", "comparable_product"]
    shared_dimension: str = Field(min_length=1, max_length=300)
    why_relevant: str = Field(min_length=1, max_length=600)
    interview_angle: str = Field(min_length=1, max_length=600)


class CompanyProfileDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    positioning: str = Field(min_length=1, max_length=700)
    business_lines: list[str] = Field(default_factory=list, max_length=8)
    key_brands: list[str] = Field(default_factory=list, max_length=8)
    key_products: list[str] = Field(default_factory=list, max_length=10)
    customer_groups: list[str] = Field(default_factory=list, max_length=8)
    strategic_focus: list[str] = Field(default_factory=list, max_length=8)
    comparable_products: list[ComparableProductDraft] = Field(default_factory=list, max_length=3)
    interview_notes: list[str] = Field(default_factory=list, max_length=4)


def normalize_company_name(company_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", company_name).casefold().strip()
    normalized = re.sub(r"\b(?:incorporated|inc|limited|ltd|corporation|corp|company|co)\b\.?", "", normalized)
    normalized = re.sub(r"(?:股份有限公司|有限责任公司|有限公司|集团)$", "", normalized)
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", normalized)


class CompanyProfileGenerator:
    def generate(self, company_name: str, *, public_evidence: list[dict] | None = None) -> CompanyProfileDraft:
        draft = ai_client.structured_completion(
            prompt_name="company_profile",
            schema=CompanyProfileDraft,
            payload={"company_name": company_name, "public_evidence": public_evidence or []},
            diagnostic_context={"flow": "company_profile_generation"},
        )
        return normalize_profile_draft(draft)

    @staticmethod
    def persistence_values(company_name: str, draft: CompanyProfileDraft, *, source_provenance: dict | None = None) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "company_name": company_name,
            **draft.model_dump(),
            "model_name": settings.openai_model,
            "generation_version": COMPANY_PROFILE_GENERATION_VERSION,
            "generated_at": now,
            "refreshed_at": now,
            "source_provenance": source_provenance or {},
        }


company_profile_generator = CompanyProfileGenerator()


def _canonical_profile_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"\bseries\b|系列", "", normalized)
    normalized = normalized.replace("xiaomi", "小米")
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", normalized)


def _dedupe_profile_names(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", value).strip()
        key = _canonical_profile_name(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _deprioritize_specific_models(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        is_specific = bool(
            re.search(r"\d+(?:\.\d+)?\s*(?:英寸|inch|[\"'“”]|gb\b|tb\b)", value, re.I)
            or (re.search(r"\d", value) and re.search(r"\b(?:oled|pro|max|ultra|5g)\b", value, re.I))
            or len(re.findall(r"\d+(?:\.\d+)?", value)) >= 2
        )
        if is_specific:
            family = re.sub(r"\s*\d.*$", "", value).strip(" -_/（(")
            family = re.sub(r"\s*(?:大师|master)\s*$", "", family, flags=re.I)
            if len(_canonical_profile_name(family)) >= 2:
                result.append(family)
            continue
        result.append(value)
    return _dedupe_profile_names(result)


def normalize_profile_draft(draft: CompanyProfileDraft) -> CompanyProfileDraft:
    brands = _deprioritize_specific_models(_dedupe_profile_names(draft.key_brands))
    products = _deprioritize_specific_models(_dedupe_profile_names(draft.key_products))
    brand_keys = {_canonical_profile_name(value) for value in brands}
    products = [value for value in products if _canonical_profile_name(value) not in brand_keys]
    return draft.model_copy(update={
        "business_lines": _dedupe_profile_names(draft.business_lines),
        "key_brands": brands,
        "key_products": products,
        "customer_groups": _dedupe_profile_names(draft.customer_groups),
        "strategic_focus": _dedupe_profile_names(draft.strategic_focus),
    })
