from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
import json
import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError, create_model

from app.core.runtime_logging import get_server_logger
from app.services.ai.client import ai_client, log_post_openai_stage, _schema_validation_diagnostic
from app.skills.company_role_research.schemas import (
    CompanyMapSection,
    CompanyMapItem,
    CompetitiveContextItem,
    CompetitiveContextSection,
    Evidence,
    FetchedSource,
    GenerationStatus,
    GroundedResearchGeneration,
    InterviewFocusItem,
    InterviewFocusSection,
    RecentSignalItem,
    RecentSignalsSection,
    ReverseQuestionItem,
    ReverseQuestionsSection,
    RoleDecoderItem,
    RoleDecoderSection,
    RoleRelevantProductItem,
    StrictModel,
    WhyCompanyRoleItem,
    WhyCompanyRoleSection,
)


MAX_GENERATION_EVIDENCE = 24
MAX_GENERATION_EVIDENCE_CHARACTERS = 24_000
MAX_SAVED_JD_CHARACTERS = 8_000
logger = get_server_logger()


class StructuredCompletionClient(Protocol):
    def structured_completion(self, **kwargs) -> GroundedResearchGeneration: ...


class GroundingValidationError(ValueError):
    def __init__(
        self,
        *,
        section: str,
        item_index: int,
        validation_rule: str,
        offending_evidence_ids: list[str] | None = None,
        offending_evidence_metadata: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(validation_rule)
        self.validation_stage = "deterministic_grounding"
        self.section = section
        self.item_index = item_index
        self.validation_rule = validation_rule
        self.offending_evidence_ids = list(offending_evidence_ids or [])[:8]
        self.offending_evidence_metadata = list(offending_evidence_metadata or [])[:8]


@dataclass(frozen=True)
class GenerationOutcome:
    report: GroundedResearchGeneration
    status: GenerationStatus
    role_relevant_products: list[RoleRelevantProductItem] = field(default_factory=list)


class WhyCompanyRoleDraftItem(StrictModel):
    """Transport shape; the canonical validator runs after deterministic wording cleanup."""

    text: str = ""
    claim_type: Literal["inference"] = "inference"
    evidence_ids: list[str] = Field(default_factory=list)


class RoleDecoderDraftItem(StrictModel):
    """Transport shape; claim type is assigned deterministically by the backend."""

    category: Literal[
        "role_goal", "core_responsibilities", "business_scenarios", "key_capabilities", "why_role_exists",
    ]
    text: str = ""
    claim_type: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class CompanyMapDraftItem(StrictModel):
    category: Literal[
        "company_positioning", "core_business", "customers", "current_focus", "financial_operating_context",
    ]
    text: str = ""
    claim_type: Literal["fact", "inference", "grounded_synthesis"]
    evidence_ids: list[str] = Field(default_factory=list)


class RecentSignalDraftItem(StrictModel):
    title: str = ""
    why_it_matters_for_interview: str = ""
    role_relevance: Literal["high", "medium", "low"]
    claim_type: Literal["fact"] = "fact"
    evidence_ids: list[str] = Field(default_factory=list)


class CompetitiveContextDraftItem(StrictModel):
    context_type: Literal["direct_competitor", "comparable_reference"]
    competitor: str = ""
    comparison_dimension: str = ""
    observed_difference: str = ""
    interview_relevance: str = ""
    what_reference_does: str | None = None
    what_target_role_emphasizes: str | None = None
    interview_takeaway: str | None = None
    claim_type: Literal["fact", "grounded_synthesis"] = "fact"
    evidence_ids: list[str] = Field(default_factory=list)


class RoleRelevantProductDraftItem(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    type: Literal["product", "platform", "brand", "ecosystem", "capability", "business"]
    relevance_to_role: str = Field(min_length=1, max_length=800)
    key_scenarios: list[str] = Field(min_length=1, max_length=5)
    things_to_understand: list[str] = Field(min_length=2, max_length=5)
    evidence_ids: list[str] = Field(default_factory=list)


class InterviewFocusDraftItem(StrictModel):
    focus_area: str = ""
    why_likely: str = ""
    likely_questions: list[str] = Field(default_factory=list)
    preparation_focus: str = ""
    confidence: Literal["high", "medium", "low"]
    claim_type: Literal["inference"] = "inference"
    evidence_ids: list[str] = Field(default_factory=list)


class ReverseQuestionDraftItem(StrictModel):
    question: str = ""
    rationale: str = ""
    claim_type: Literal["inference"] = "inference"
    evidence_ids: list[str] = Field(default_factory=list)


def unavailable_report() -> GroundedResearchGeneration:
    return GroundedResearchGeneration(
        company_map=CompanyMapSection(status="unavailable"),
        role_decoder=RoleDecoderSection(status="unavailable"),
        recent_signals=RecentSignalsSection(status="unavailable"),
        competitive_context=CompetitiveContextSection(status="unavailable"),
        likely_interview_focus=InterviewFocusSection(status="unavailable"),
        why_company_why_role_60s=WhyCompanyRoleSection(status="unavailable"),
        reverse_questions=ReverseQuestionsSection(status="unavailable"),
    )


class GroundedResearchGenerator:
    """Single-call structured generation followed by deterministic grounding checks."""

    def __init__(self, client: StructuredCompletionClient = ai_client) -> None:
        self.client = client

    def generate(
        self,
        *,
        company_name: str,
        job_title: str | None,
        saved_jd: str | None,
        evidence: list[Evidence],
        fetched_sources: list[FetchedSource],
        company_profile_context: dict[str, object] | None = None,
        supply_diagnostics: dict[str, dict[str, int]] | None = None,
        competitive_candidate_bindings: list[dict[str, object]] | None = None,
    ) -> GenerationOutcome:
        diagnostics = self._empty_supply_diagnostics()
        for section, counts in (supply_diagnostics or {}).items():
            if section in diagnostics:
                diagnostics[section].update(counts)
        selected = self._select_evidence(evidence)
        if not selected:
            self._log_supply_diagnostics(diagnostics)
            return GenerationOutcome(unavailable_report(), "unavailable")
        source_metadata = {
            source.source_id: {
                "title": source.title,
                "url": source.url,
                "published_at": source.published_at,
                "source_type": source.source_type,
            }
            for source in fetched_sources
        }
        for item in selected:
            if item.source_type == "ai_inference":
                source_metadata.setdefault(item.source_id, {
                    "title": "AI-generated company profile",
                    "url": None,
                    "published_at": None,
                    "source_type": "ai_inference",
                })
        submitted = {item.evidence_id: item for item in selected}
        candidate_bindings = (
            self._prepare_competitive_candidate_bindings(competitive_candidate_bindings, submitted)
            if competitive_candidate_bindings is not None
            else None
        )
        company_aliases = self._build_company_aliases(company_name, submitted, source_metadata)
        owned_entity_aliases = self._build_owned_entity_aliases(company_aliases, submitted, source_metadata)
        allowed_evidence_by_section = self._allowed_evidence_by_section(submitted)
        if candidate_bindings is not None:
            allowed_evidence_by_section["competitive_context"] = list(dict.fromkeys(
                evidence_id
                for binding in candidate_bindings
                for evidence_id in (
                    *binding["reference_side_evidence_ids"],
                    *binding["target_side_evidence_ids"],
                )
            ))
        for section in diagnostics:
            diagnostics[section]["routed_evidence_count"] = len(allowed_evidence_by_section[section])
        competitive_guidance = self._competitive_evidence_guidance(
            submitted, company_aliases, owned_entity_aliases,
        )
        diagnostics["competitive_context"]["candidate_reference_count"] = sum(
            item.get("candidate_type") == "comparable_reference_candidate"
            and bool(item.get("named_entities"))
            for item in competitive_guidance.values()
        )
        response_schema = self._build_response_schema(allowed_evidence_by_section)
        transport_schema = self._build_transport_schema(
            allowed_evidence_by_section,
            candidate_bindings,
        )
        payload_allowed_evidence = {
            section: list(evidence_ids)
            for section, evidence_ids in allowed_evidence_by_section.items()
        }
        if candidate_bindings is not None:
            payload_allowed_evidence["competitive_context"] = [
                str(binding["citation_alias"]) for binding in candidate_bindings
            ]
        payload_evidence = []
        saved_jd_payload = None
        for item in selected:
            record = {
                "evidence_id": item.evidence_id,
                "source_id": item.source_id,
                "source_type": item.source_type,
                "evidence_type": item.evidence_type,
                "text": (
                    (saved_jd or item.text)[:MAX_SAVED_JD_CHARACTERS]
                    if item.source_type == "user_provided"
                    else item.text
                ),
                "source": source_metadata.get(item.source_id, {
                    "title": "Saved job description",
                    "url": None,
                    "published_at": None,
                    "source_type": "user_provided",
                }),
            }
            if item.source_type == "user_provided":
                saved_jd_payload = record
            else:
                payload_evidence.append(record)
        try:
            report = self.client.structured_completion(
                prompt_name="company_role_research",
                schema=transport_schema,
                payload={
                    "company_name": company_name,
                    "job_title": job_title,
                    "saved_jd": saved_jd_payload,
                    "evidence": payload_evidence,
                    "allowed_evidence_by_section": payload_allowed_evidence,
                    "competitive_evidence_guidance": competitive_guidance,
                    "competitive_candidate_bindings": candidate_bindings or [],
                    "knowledge_only": any(item.source_type == "ai_inference" for item in selected),
                    "company_profile": company_profile_context or {},
                },
                diagnostic_context={"flow": "company_role_research_generation"},
            )
            if isinstance(report, BaseModel):
                raw_report = report.model_dump()
            else:
                for item in report.get("recent_signals", {}).get("items", []):
                    item.pop("date", None)
                raw_report = transport_schema.model_validate(report).model_dump()
        except Exception as exc:
            self._log_fallback("failed", exc)
            return GenerationOutcome(unavailable_report(), "failed")

        generated_role_products = raw_report.pop("role_relevant_products_and_scenarios", [])
        valid_role_products: list[RoleRelevantProductItem] = []
        dropped_role_products = {"missing_company_evidence": 0, "missing_role_evidence": 0, "malformed_item": 0}
        for item in generated_role_products:
            cited = [submitted.get(evidence_id) for evidence_id in item.get("evidence_ids", [])]
            if not any(evidence and evidence.evidence_type == "company" for evidence in cited):
                dropped_role_products["missing_company_evidence"] += 1
                continue
            if not any(evidence and evidence.evidence_type == "role" for evidence in cited):
                dropped_role_products["missing_role_evidence"] += 1
                continue
            try:
                valid_role_products.append(RoleRelevantProductItem.model_validate({
                    key: value for key, value in item.items() if key != "evidence_ids"
                }))
            except ValidationError:
                dropped_role_products["malformed_item"] += 1
                continue
        logger.info(
            "company_research_role_products_generation %s",
            json.dumps({
                "generated_item_count": len(generated_role_products),
                "valid_item_count": len(valid_role_products),
                **dropped_role_products,
            }, separators=(",", ":")),
        )

        for item in raw_report.get("recent_signals", {}).get("items", []):
            item.pop("date", None)
        competitive_alias_errors = (
            self._expand_competitive_citation_aliases(raw_report, candidate_bindings)
            if candidate_bindings is not None
            else []
        )
        self._assign_role_decoder_claim_types(raw_report)
        rewritten_terms = self._normalize_why_company_role(raw_report)
        if rewritten_terms:
            logger.info(
                "company_research_why_wording_normalized %s",
                json.dumps({"matched_terms": rewritten_terms}, ensure_ascii=False, separators=(",", ":")),
            )

        section_names = tuple(GroundedResearchGeneration.model_fields)
        final_sections = unavailable_report().model_dump()
        degraded_sections: list[str] = []
        for section in section_names:
            raw_section = raw_report[section]
            raw_items = list(raw_section.get("items", []))
            if section == "competitive_context" and competitive_alias_errors:
                invalid_indexes = {int(error["item_index"]) for error in competitive_alias_errors}
                raw_items = [item for index, item in enumerate(raw_items) if index not in invalid_indexes]
                for error in competitive_alias_errors:
                    self._log_item_dropped(
                        section,
                        int(error["item_index"]),
                        str(error["validation_rule"]),
                        len(raw_items),
                        field="evidence_ids",
                        error_type="AliasExpansionError",
                        expected_constraint=str(error["expected_constraint"]),
                    )
            fallback_reference = None
            if section == "competitive_context" and candidate_bindings is None:
                fallback_reference = self._build_comparable_reference_fallback(
                    submitted, company_aliases, owned_entity_aliases,
                )
                if fallback_reference and len(raw_items) < 3 and not any(
                    item.get("competitor") == fallback_reference["competitor"] for item in raw_items
                ):
                    raw_items.append(fallback_reference)
            if raw_section.get("status") == "unavailable" and not raw_items:
                continue
            if section == "recent_signals":
                before_anchor_count = len(raw_items)
                raw_items = self._filter_recent_company_anchors(
                    raw_items, submitted, source_metadata, company_aliases,
                )
                diagnostics[section]["dropped_missing_company_anchor"] += before_anchor_count - len(raw_items)
            working_items, deduped = self._preprocess_section_items(section, raw_items, submitted)
            fallback_used = bool(fallback_reference and any(
                item.get("competitor") == fallback_reference["competitor"] for item in working_items
            ))
            for item_index, rule in deduped:
                if section == "recent_signals" and rule == "low_role_relevance":
                    diagnostics[section]["dropped_low_role_relevance"] += 1
                if section == "recent_signals" and rule == "duplicate_event":
                    diagnostics[section]["dropped_duplicate_event"] += 1
                self._log_item_dropped(section, item_index, rule, len(working_items))
            if section == "recent_signals" and len(working_items) == 1 and working_items[0].get("role_relevance") == "high":
                logger.info("company_research_sparse_but_high_quality %s", json.dumps({"section": section, "item_count": 1}, separators=(",", ":")))
            while True:
                if not self._meets_section_minimum(section, working_items):
                    if section == "competitive_context" and fallback_reference and not fallback_used:
                        working_items = [fallback_reference]
                        fallback_used = True
                        continue
                    degraded_sections.append(section)
                    self._log_below_minimum(section, len(working_items))
                    break
                try:
                    constrained_candidate = unavailable_report().model_dump()
                    constrained_candidate[section] = {"status": "available", "items": working_items}
                    constrained = response_schema.model_validate(constrained_candidate).model_dump()
                    section_payload = constrained[section]
                    if section == "recent_signals":
                        wrapper = {"recent_signals": section_payload}
                        self._fill_recent_signal_dates(wrapper, submitted, source_metadata)
                        section_payload = wrapper["recent_signals"]
                    canonical_candidate = unavailable_report().model_dump()
                    canonical_candidate[section] = section_payload
                    canonical = GroundedResearchGeneration.model_validate(canonical_candidate)
                    self._validate_grounding(
                        canonical,
                        submitted,
                        source_metadata,
                        company_aliases,
                        owned_entity_aliases,
                    )
                    final_sections[section] = getattr(canonical, section).model_dump()
                    break
                except ValidationError as exc:
                    diagnostic = _schema_validation_diagnostic(exc)
                    item_index = diagnostic.get("item_index")
                    if not isinstance(item_index, int) or item_index >= len(working_items):
                        degraded_sections.append(section)
                        log_post_openai_stage("schema_validation_failed", "company_role_research_section_validation", exc=exc, parsed_output_present=True)
                        self._log_section_degraded(section, exc)
                        break
                    working_items.pop(item_index)
                    self._log_item_dropped(
                        section,
                        item_index,
                        str(diagnostic.get("validation_rule") or "malformed_item"),
                        len(working_items),
                        field=diagnostic.get("field"),
                        error_type=diagnostic.get("error_type"),
                        expected_constraint=diagnostic.get("expected_constraint"),
                    )
                except GroundingValidationError as exc:
                    if exc.item_index >= len(working_items):
                        degraded_sections.append(section)
                        self._log_section_degraded(section, exc)
                        break
                    working_items.pop(exc.item_index)
                    if section == "competitive_context":
                        diagnostic_key = {
                            "missing_specific_reference": "dropped_missing_specific_entity",
                            "missing_shared_dimension": "dropped_missing_shared_dimension",
                            "unsupported_reference_point": "dropped_unsupported_reference_point",
                        }.get(exc.validation_rule)
                        if diagnostic_key:
                            diagnostics[section][diagnostic_key] += 1
                    validation_rule = "invalid_date_metadata" if (
                        section == "recent_signals" and exc.validation_rule == "date_not_supported"
                    ) else exc.validation_rule
                    if section == "why_company_why_role_60s" and validation_rule in {
                        "invalid_evidence_id", "wrong_evidence_type", "missing_company_or_role_evidence",
                    }:
                        validation_rule = "unsupported_evidence"
                    self._log_item_dropped(
                        section,
                        exc.item_index,
                        validation_rule,
                        len(working_items),
                        field=(
                            "date" if validation_rule == "invalid_date_metadata"
                            else "evidence_ids" if validation_rule == "unsupported_evidence"
                            else "text" if section == "why_company_why_role_60s" else None
                        ),
                        error_type=type(exc).__name__,
                        expected_constraint=(
                            "backend_derived_source_date" if validation_rule == "invalid_date_metadata"
                            else "company_and_role_allowed_evidence" if validation_rule == "unsupported_evidence"
                            else "no_candidate_fit" if validation_rule == "candidate_fit_material"
                            else None
                        ),
                    )
                except Exception as exc:
                    self._log_fallback("failed", exc)
                    return GenerationOutcome(unavailable_report(), "failed")

        report = GroundedResearchGeneration.model_validate(final_sections)
        for section in diagnostics:
            diagnostics[section]["valid_item_count"] = len(getattr(report, section).items)
        self._log_supply_diagnostics(diagnostics)
        available_count = sum(getattr(report, section).status == "available" for section in section_names)
        if available_count == 0:
            status: GenerationStatus = "unavailable"
        elif degraded_sections:
            status = "partial"
        else:
            status = "generated"
        if degraded_sections:
            logger.warning(
                "company_research_generation_partial %s",
                json.dumps({
                    "generation_status": status,
                    "degraded_sections": degraded_sections,
                }, separators=(",", ":")),
            )
        return GenerationOutcome(report, status, valid_role_products)

    @staticmethod
    def _log_supply_diagnostics(diagnostics: dict[str, dict[str, int]]) -> None:
        for section in ("company_map", "recent_signals", "competitive_context"):
            logger.warning(
                "company_research_evidence_supply %s",
                json.dumps({"section": section, **diagnostics.get(section, {})}, separators=(",", ":")),
            )

    @staticmethod
    def _empty_supply_diagnostics() -> dict[str, dict[str, int]]:
        common = {
            "discovered_candidate_count": 0,
            "fetch_attempt_count": 0,
            "fetch_success_count": 0,
            "extracted_evidence_count": 0,
            "routed_evidence_count": 0,
            "valid_item_count": 0,
        }
        return {
            "company_map": {
                **common,
                "company_positioning_evidence_count": 0,
                "core_business_evidence_count": 0,
                "customers_evidence_count": 0,
                "current_focus_evidence_count": 0,
            },
            "recent_signals": {
                **common,
                "dropped_missing_company_anchor": 0,
                "dropped_outside_90_days": 0,
                "dropped_low_role_relevance": 0,
                "dropped_duplicate_event": 0,
            },
            "competitive_context": {
                **common,
                "candidate_reference_count": 0,
                "dropped_missing_specific_entity": 0,
                "dropped_missing_shared_dimension": 0,
                "dropped_unsupported_reference_point": 0,
            },
        }

    @staticmethod
    def _select_evidence(evidence: list[Evidence]) -> list[Evidence]:
        priority = {"user_provided": 0, "ai_inference": 1, "official": 2, "external": 3, "campus": 4, "community": 5}
        unique = {item.evidence_id: item for item in evidence}
        ordered = sorted(unique.values(), key=lambda item: priority[item.source_type])
        evidence_types = (
            "company",
            "role",
            "recent_signal",
            "competitive",
            "campus_recruitment",
            "interview_experience",
        )
        buckets = {
            evidence_type: [item for item in ordered if item.evidence_type == evidence_type]
            for evidence_type in evidence_types
        }
        selected: list[Evidence] = []
        used_characters = 0
        while len(selected) < MAX_GENERATION_EVIDENCE:
            made_progress = False
            for evidence_type in evidence_types:
                if not buckets[evidence_type]:
                    continue
                made_progress = True
                item = buckets[evidence_type].pop(0)
                text_limit = MAX_SAVED_JD_CHARACTERS if item.source_type == "user_provided" else len(item.text)
                available = MAX_GENERATION_EVIDENCE_CHARACTERS - used_characters
                text = item.text[:min(text_limit, available)]
                if not text:
                    return selected
                selected.append(item.model_copy(update={"text": text}))
                used_characters += len(text)
                if len(selected) >= MAX_GENERATION_EVIDENCE:
                    return selected
            if not made_progress:
                break
        return selected

    def _validate_grounding(
        self,
        report: GroundedResearchGeneration,
        evidence: dict[str, Evidence],
        source_metadata: dict[str, dict],
        company_aliases: set[str] | None = None,
        owned_entity_aliases: set[str] | None = None,
    ) -> None:
        company_rule = lambda item: self._evidence_allowed("company_map", item)
        role_rule = lambda item: self._evidence_allowed("role_decoder", item)
        recent_rule = lambda item: self._evidence_allowed("recent_signals", item)
        competitive_rule = lambda item: self._evidence_allowed("competitive_context", item)
        interview_rule = lambda item: self._evidence_allowed("likely_interview_focus", item)
        reverse_rule = lambda item: self._evidence_allowed("reverse_questions", item)

        for index, item in enumerate(report.company_map.items):
            refs = self._validate_ids(item.evidence_ids, evidence, company_rule, "company_map", index)
            self._validate_company_map_item(item, refs, index)
        for index, item in enumerate(report.role_decoder.items):
            self._validate_ids(item.evidence_ids, evidence, role_rule, "role_decoder", index)
            expected = "fact" if item.category in {"core_responsibilities", "key_capabilities"} else "inference"
            if item.claim_type != expected:
                raise GroundingValidationError(
                    section="role_decoder",
                    item_index=index,
                    validation_rule="claim_type_mismatch",
                    offending_evidence_ids=item.evidence_ids,
                )
        for index, item in enumerate(report.recent_signals.items):
            refs = self._validate_ids(item.evidence_ids, evidence, recent_rule, "recent_signals", index)
            expected_date = self._source_published_date(refs, source_metadata)
            if item.date != expected_date:
                raise GroundingValidationError(
                    section="recent_signals",
                    item_index=index,
                    validation_rule="date_not_supported",
                    offending_evidence_ids=item.evidence_ids,
                    offending_evidence_metadata=[{
                        "evidence_id": ref.evidence_id,
                        "source_type": ref.source_type,
                        "evidence_type": ref.evidence_type,
                        "published_at": str(source_metadata.get(ref.source_id, {}).get("published_at")),
                    } for ref in refs],
                )
        for index, item in enumerate(report.competitive_context.items):
            refs = self._validate_ids(item.evidence_ids, evidence, competitive_rule, "competitive_context", index)
            if self._entity_is_target_owned(
                item.competitor,
                company_aliases or set(),
                owned_entity_aliases or set(),
            ):
                raise GroundingValidationError(
                    section="competitive_context",
                    item_index=index,
                    validation_rule="target_company_owned_entity",
                    offending_evidence_ids=item.evidence_ids,
                )
            if item.context_type == "direct_competitor":
                self._validate_competitive_relation(item, refs, company_aliases or set(), index)
            else:
                self._validate_comparable_reference(item, refs, company_aliases or set(), index)
        for index, item in enumerate(report.likely_interview_focus.items):
            self._validate_ids(item.evidence_ids, evidence, interview_rule, "likely_interview_focus", index)
        for index, item in enumerate(report.reverse_questions.items):
            self._validate_ids(item.evidence_ids, evidence, reverse_rule, "reverse_questions", index)
        for index, item in enumerate(report.why_company_why_role_60s.items):
            refs = self._validate_ids(
                item.evidence_ids,
                evidence,
                lambda evidence_item: company_rule(evidence_item) or role_rule(evidence_item),
                "why_company_why_role_60s",
                index,
            )
            if not any(company_rule(ref) for ref in refs) or not any(role_rule(ref) for ref in refs):
                raise GroundingValidationError(
                    section="why_company_why_role_60s",
                    item_index=index,
                    validation_rule="missing_company_or_role_evidence",
                    offending_evidence_ids=item.evidence_ids,
                )
            if re.search(r"我的简历|我的经历|过往经历|我曾|我的项目|my resume|my experience", item.text, re.I):
                raise GroundingValidationError(
                    section="why_company_why_role_60s",
                    item_index=index,
                    validation_rule="candidate_fit_material",
                    offending_evidence_ids=item.evidence_ids,
                )

    @staticmethod
    def _validate_ids(evidence_ids, evidence, rule, section, item_index):
        refs = []
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise GroundingValidationError(
                    section=section,
                    item_index=item_index,
                    validation_rule="unknown_evidence_id",
                    offending_evidence_ids=[evidence_id],
                )
            item = evidence[evidence_id]
            if not rule(item):
                raise GroundingValidationError(
                    section=section,
                    item_index=item_index,
                    validation_rule="wrong_evidence_type",
                    offending_evidence_ids=[evidence_id],
                    offending_evidence_metadata=[{
                        "evidence_id": evidence_id,
                        "source_type": item.source_type,
                        "evidence_type": item.evidence_type,
                    }],
                )
            refs.append(item)
        return refs

    @classmethod
    def _allowed_evidence_by_section(cls, evidence: dict[str, Evidence]) -> dict[str, list[str]]:
        sections = (
            "company_map",
            "role_decoder",
            "recent_signals",
            "competitive_context",
            "likely_interview_focus",
            "why_company_why_role_60s",
            "reverse_questions",
        )
        allowed = {
            section: [
                evidence_id
                for evidence_id, item in evidence.items()
                if cls._evidence_allowed(section, item)
            ]
            for section in sections
        }
        # Target-side context alone must never activate Competitive Context.
        # It becomes available only when at least one real competitive evidence
        # record exists, at which point target evidence may ground the other side.
        if not any(
            item.evidence_type == "competitive" and item.source_type in {"official", "external"}
            for item in evidence.values()
        ):
            allowed["competitive_context"] = []
        return allowed

    @staticmethod
    def _build_response_schema(
        allowed_evidence_by_section: dict[str, list[str]],
    ) -> type[GroundedResearchGeneration]:
        section_specs = {
            "company_map": (CompanyMapItem, CompanyMapSection, 5, 1, 8),
            "role_decoder": (RoleDecoderItem, RoleDecoderSection, 5, 1, 8),
            "recent_signals": (RecentSignalItem, RecentSignalsSection, 4, 1, 8),
            "competitive_context": (CompetitiveContextItem, CompetitiveContextSection, 3, 1, 8),
            "likely_interview_focus": (InterviewFocusItem, InterviewFocusSection, 5, 1, 8),
            "why_company_why_role_60s": (WhyCompanyRoleItem, WhyCompanyRoleSection, 1, 2, 8),
            "reverse_questions": (ReverseQuestionItem, ReverseQuestionsSection, 5, 1, 8),
        }
        dynamic_sections: dict[str, type[BaseModel]] = {}
        for section, (item_base, section_base, max_items, min_evidence, max_evidence) in section_specs.items():
            allowed_ids = allowed_evidence_by_section[section]
            model_prefix = "".join(part.title() for part in section.split("_"))
            if not allowed_ids:
                dynamic_sections[section] = create_model(
                    f"{model_prefix}UnavailableSection",
                    __base__=section_base,
                    status=(Literal["unavailable"], "unavailable"),
                    items=(list[item_base], Field(default_factory=list, max_length=0)),
                )
                continue
            evidence_id_enum = Literal.__getitem__(tuple(allowed_ids))
            if section == "recent_signals":
                constrained_item = create_model(
                    f"{model_prefix}ConstrainedItem",
                    __base__=StrictModel,
                    title=(str, Field(min_length=1, max_length=1_500)),
                    why_it_matters_for_interview=(str, Field(min_length=1, max_length=1_000)),
                    role_relevance=(Literal["high", "medium", "low"], ...),
                    claim_type=(Literal["fact"], "fact"),
                    evidence_ids=(
                        list[evidence_id_enum],
                        Field(min_length=min_evidence, max_length=max_evidence),
                    ),
                )
            else:
                constrained_base = {
                    "role_decoder": RoleDecoderDraftItem,
                    "why_company_why_role_60s": WhyCompanyRoleDraftItem,
                }.get(section, item_base)
                constrained_item = create_model(
                    f"{model_prefix}ConstrainedItem",
                    __base__=constrained_base,
                    evidence_ids=(
                        list[evidence_id_enum],
                        Field(min_length=min_evidence, max_length=max_evidence),
                    ),
                )
            dynamic_sections[section] = create_model(
                f"{model_prefix}ConstrainedSection",
                __base__=section_base,
                items=(list[constrained_item], Field(default_factory=list, max_length=max_items)),
            )
        return create_model(
            "GroundedResearchGenerationWithEvidenceEnums",
            __base__=GroundedResearchGeneration,
            **{
                section: (section_model, ...)
                for section, section_model in dynamic_sections.items()
            },
        )

    @staticmethod
    def _build_transport_schema(
        allowed_evidence_by_section: dict[str, list[str]],
        competitive_candidate_bindings: list[dict[str, object]] | None = None,
    ) -> type[BaseModel]:
        item_models = {
            "company_map": CompanyMapDraftItem,
            "role_decoder": RoleDecoderDraftItem,
            "recent_signals": RecentSignalDraftItem,
            "competitive_context": CompetitiveContextDraftItem,
            "likely_interview_focus": InterviewFocusDraftItem,
            "why_company_why_role_60s": WhyCompanyRoleDraftItem,
            "reverse_questions": ReverseQuestionDraftItem,
        }
        section_models = {}
        for section, item_model in item_models.items():
            allowed_ids = allowed_evidence_by_section[section]
            if section == "competitive_context" and competitive_candidate_bindings == []:
                section_models[section] = create_model(
                    "CompetitiveContextUnavailableTransportSection",
                    __base__=StrictModel,
                    status=(Literal["unavailable"], "unavailable"),
                    items=(list[CompetitiveContextDraftItem], Field(default_factory=list, max_length=0)),
                )
                continue
            constrained_item = item_model
            if section == "competitive_context" and competitive_candidate_bindings:
                citation_aliases = tuple(
                    str(binding["citation_alias"])
                    for binding in competitive_candidate_bindings
                )
                alias_enum = Literal.__getitem__(citation_aliases)
                constrained_item = create_model(
                    "CompetitiveCandidateCitationTransportItem",
                    __base__=CompetitiveContextDraftItem,
                    evidence_ids=(list[alias_enum], Field(min_length=1, max_length=1)),
                )
            if allowed_ids:
                if section != "competitive_context" or not competitive_candidate_bindings:
                    evidence_id_enum = Literal.__getitem__(tuple(allowed_ids))
                    constrained_item = create_model(
                        f"{''.join(part.title() for part in section.split('_'))}TransportItem",
                        __base__=item_model,
                        evidence_ids=(list[evidence_id_enum], Field(default_factory=list)),
                    )
            section_models[section] = create_model(
                f"{''.join(part.title() for part in section.split('_'))}TransportSection",
                __base__=StrictModel,
                status=(Literal["available", "unavailable"], ...),
                items=(list[constrained_item], Field(default_factory=list)),
            )
        role_product_ids = list(dict.fromkeys([
            *allowed_evidence_by_section["company_map"],
            *allowed_evidence_by_section["role_decoder"],
        ]))
        role_product_model: type[BaseModel] = RoleRelevantProductDraftItem
        if role_product_ids:
            role_product_enum = Literal.__getitem__(tuple(role_product_ids))
            role_product_model = create_model(
                "RoleRelevantProductTransportItem",
                __base__=RoleRelevantProductDraftItem,
                evidence_ids=(list[role_product_enum], Field(min_length=2, max_length=8)),
            )
        return create_model(
            "GroundedResearchGenerationTransport",
            __base__=StrictModel,
            role_relevant_products_and_scenarios=(
                list[role_product_model],
                Field(default_factory=list, max_length=5),
            ),
            **{section: (model, ...) for section, model in section_models.items()},
        )

    @staticmethod
    def _prepare_competitive_candidate_bindings(
        bindings: list[dict[str, object]],
        submitted: dict[str, Evidence],
    ) -> list[dict[str, object]]:
        prepared: list[dict[str, object]] = []
        for binding_index, binding in enumerate(bindings, start=1):
            reference_ids = [
                str(evidence_id) for evidence_id in binding.get("reference_side_evidence_ids", [])
                if evidence_id in submitted
                and submitted[str(evidence_id)].evidence_type == "competitive"
                and submitted[str(evidence_id)].source_type == "external"
            ]
            target_ids = [
                str(evidence_id) for evidence_id in binding.get("target_side_evidence_ids", [])
                if evidence_id in submitted
                and submitted[str(evidence_id)].evidence_type in {"company", "role"}
            ]
            if not reference_ids or not target_ids:
                logger.warning(
                    "company_research_competitor_handoff %s",
                    json.dumps({
                        "candidate_name": str(binding.get("entity") or "unknown")[:120],
                        "validation_rule": "candidate_skipped_missing_reference_evidence"
                        if not reference_ids else "candidate_skipped_missing_target_evidence",
                        "reference_side_evidence_count": len(reference_ids),
                        "target_side_evidence_count": len(target_ids),
                        "action": "candidate_skipped_before_generation",
                    }, separators=(",", ":")),
                )
                continue
            prepared.append({
                "citation_alias": f"competitive_candidate_{binding_index}",
                "entity": str(binding["entity"]),
                "candidate_type": str(binding["candidate_type"]),
                "candidate_category": str(binding.get("candidate_category") or "same_agent_platform"),
                "shared_dimensions": list(binding.get("shared_dimensions", [])),
                "reference_side_evidence_ids": reference_ids,
                "target_side_evidence_ids": target_ids,
            })
        return prepared

    @staticmethod
    def _expand_competitive_citation_aliases(
        report_payload: dict,
        bindings: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        by_alias = {str(binding["citation_alias"]): binding for binding in bindings}
        errors: list[dict[str, object]] = []
        section = report_payload.get("competitive_context")
        if not isinstance(section, dict):
            return errors
        for item_index, item in enumerate(section.get("items", [])):
            if not isinstance(item, dict):
                errors.append({
                    "item_index": item_index,
                    "validation_rule": "malformed_evidence_ids",
                    "expected_constraint": "single_valid_candidate_citation_alias",
                })
                continue
            aliases = item.get("evidence_ids")
            if not isinstance(aliases, list):
                errors.append({
                    "item_index": item_index,
                    "validation_rule": "malformed_evidence_ids",
                    "expected_constraint": "single_alias_list",
                })
                continue
            if len(aliases) != 1 or not isinstance(aliases[0], str):
                errors.append({
                    "item_index": item_index,
                    "validation_rule": "invalid_evidence_alias" if aliases else "malformed_evidence_ids",
                    "expected_constraint": "exactly_one_candidate_citation_alias",
                })
                continue
            alias = aliases[0]
            binding = by_alias.get(alias)
            if not binding:
                errors.append({
                    "item_index": item_index,
                    "validation_rule": "invalid_evidence_alias",
                    "expected_constraint": "alias_from_competitive_candidate_bindings",
                })
                continue
            reference_ids = [str(value) for value in binding.get("reference_side_evidence_ids", []) if value]
            target_ids = [str(value) for value in binding.get("target_side_evidence_ids", []) if value]
            if not reference_ids:
                errors.append({
                    "item_index": item_index,
                    "validation_rule": "missing_reference_alias",
                    "expected_constraint": "at_least_one_reference_side_evidence_id",
                })
                continue
            if not target_ids:
                errors.append({
                    "item_index": item_index,
                    "validation_rule": "missing_target_alias",
                    "expected_constraint": "at_least_one_target_side_evidence_id",
                })
                continue
            expanded_ids = list(dict.fromkeys((reference_ids[0], target_ids[0])))
            if len(expanded_ids) != 2:
                errors.append({
                    "item_index": item_index,
                    "validation_rule": "alias_expansion_failed",
                    "expected_constraint": "distinct_reference_and_target_evidence_ids",
                })
                continue
            item["competitor"] = str(binding["entity"])
            item["evidence_ids"] = expanded_ids
            logger.warning(
                "company_research_competitive_alias_expansion %s",
                json.dumps({
                    "item_index": item_index,
                    "citation_alias": alias,
                    "expanded_evidence_ids": expanded_ids,
                    "reference_side_count": 1,
                    "target_side_count": 1,
                }, separators=(",", ":")),
            )
        for error in errors:
            logger.warning(
                "company_research_competitive_alias_error %s",
                json.dumps({
                    "section": "competitive_context",
                    "item_index": error["item_index"],
                    "field": "evidence_ids",
                    "validation_rule": error["validation_rule"],
                    "expected_constraint": error["expected_constraint"],
                    "error_type": "AliasExpansionError",
                }, separators=(",", ":")),
            )
        return errors

    @staticmethod
    def _assign_role_decoder_claim_types(report_payload: dict) -> None:
        claim_types = {
            "role_goal": "inference",
            "core_responsibilities": "fact",
            "business_scenarios": "inference",
            "key_capabilities": "fact",
            "why_role_exists": "inference",
        }
        section = report_payload.get("role_decoder")
        if not isinstance(section, dict):
            return
        items = section.get("items")
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, dict) and item.get("category") in claim_types:
                item["claim_type"] = claim_types[item["category"]]

    @staticmethod
    def _normalize_why_company_role(report_payload: dict) -> list[str]:
        """Rewrite only known promotional wording before canonical schema validation."""
        replacements = (
            ("深厚积累", "长期投入"),
            ("创新活力", "持续做新产品"),
            ("前瞻战略", "当前重点方向"),
            ("技术实力雄厚", "有相关技术和产品实践"),
            ("行业领先", "在相关领域持续投入"),
            ("引领创新", "持续改进产品"),
            ("深度融合", "结合"),
            ("持续赋能", "持续支持"),
            ("赋能", "支持"),
            ("助力公司", "推动"),
            ("全流程管理", "从方案到落地"),
            ("实现成长和贡献", "继续深入这个方向"),
            ("技术与业务双重领先", "技术和业务都在持续推进"),
            ("创新让产品富有竞争力", "持续改进产品"),
            ("富有竞争力", "更好用"),
            ("前瞻布局", "当前投入"),
            ("技术实力", "相关技术和产品实践"),
        )
        matched: list[str] = []
        section = report_payload.get("why_company_why_role_60s")
        if not isinstance(section, dict):
            return matched
        items = section.get("items")
        if not isinstance(items, list):
            return matched
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            text = item["text"]
            for phrase, replacement in replacements:
                if phrase in text:
                    matched.append(phrase)
                    text = text.replace(phrase, replacement)
            role_markers = ("这个岗位吸引", "岗位吸引", "选择这个岗位", "岗位本身")
            if not any(marker in text for marker in role_markers) and "岗位" in text:
                text = text.replace("岗位", "这个岗位吸引我的地方是，岗位", 1)
                matched.append("missing_role_reason")
            motivation_markers = ("对我来说", "我希望继续", "我想继续", "很有吸引力", "我愿意继续")
            if not any(marker in text for marker in motivation_markers):
                motivation = "对我来说，这类工作很有吸引力，也是我希望继续深入的方向。"
                available_prefix = 220 - len(motivation)
                if len(text) > available_prefix:
                    prefix = text[:available_prefix]
                    boundary = max(prefix.rfind(mark) for mark in "。！？")
                    text = prefix[:boundary + 1] if boundary >= 120 else prefix
                text = text.rstrip("，,；;：: ") + motivation
                matched.append("missing_personal_motivation")
            text = re.sub(r"聚焦于(.{1,40}?)的发展", r"关注\1", text)
            for duplicated, replacement in (
                ("这个这个", "这个"),
                ("岗位岗位", "岗位"),
                ("公司公司", "公司"),
            ):
                if duplicated in text:
                    matched.append(duplicated)
                    text = text.replace(duplicated, replacement)
            item["text"] = text
        return list(dict.fromkeys(matched))

    @staticmethod
    def _evidence_allowed(section: str, item: Evidence) -> bool:
        is_company = item.evidence_type == "company" and item.source_type in {"official", "external", "ai_inference"}
        is_role = item.evidence_type == "role" and item.source_type in {"user_provided", "official", "campus"}
        is_recent = item.evidence_type == "recent_signal" and item.source_type in {"official", "external"}
        is_competitive = item.evidence_type == "competitive" and item.source_type in {"official", "external"}
        is_interview_experience = item.evidence_type == "interview_experience" and item.source_type == "community"
        policies = {
            "company_map": is_company,
            "role_decoder": is_role,
            "recent_signals": is_recent,
            # Comparable references need both sides of a bounded comparison:
            # external reference evidence plus target company/role/JD evidence.
            "competitive_context": is_competitive or is_company or is_role,
            "likely_interview_focus": is_company or is_role or is_recent or is_interview_experience,
            "why_company_why_role_60s": is_company or is_role,
            "reverse_questions": is_company or is_role or is_recent or is_competitive,
        }
        return policies.get(section, False)

    @classmethod
    def _fill_recent_signal_dates(
        cls,
        report_payload: dict,
        evidence: dict[str, Evidence],
        source_metadata: dict[str, dict],
    ) -> None:
        for item in report_payload.get("recent_signals", {}).get("items", []):
            refs = [evidence[evidence_id] for evidence_id in item["evidence_ids"] if evidence_id in evidence]
            item["date"] = cls._source_published_date(refs, source_metadata)

    @classmethod
    def _source_published_date(
        cls,
        refs: list[Evidence],
        source_metadata: dict[str, dict],
    ) -> str | None:
        dates = {
            normalized
            for ref in refs
            if (normalized := cls._normalize_date(source_metadata.get(ref.source_id, {}).get("published_at")))
        }
        return next(iter(dates)) if len(dates) == 1 else None

    @staticmethod
    def _normalize_date(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(text).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return None

    @classmethod
    def _build_company_aliases(
        cls,
        company_name: str,
        evidence: dict[str, Evidence],
        source_metadata: dict[str, dict],
    ) -> set[str]:
        aliases = {company_name.casefold().strip()}
        generic = {"company", "official", "group", "news", "career", "careers", "ai", "agent", "llm"}
        anchored_texts: list[str] = []
        for item in evidence.values():
            metadata = source_metadata.get(item.source_id, {})
            title = str(metadata.get("title") or "")
            if item.source_type == "official":
                anchored_texts.append(title)
        for text in anchored_texts:
            for token in re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}\b", text):
                normalized = token.casefold()
                if normalized not in generic:
                    aliases.add(normalized)
        return {alias for alias in aliases if len(alias) >= 2}

    @classmethod
    def _build_owned_entity_aliases(
        cls,
        company_aliases: set[str],
        evidence: dict[str, Evidence],
        source_metadata: dict[str, dict] | None = None,
    ) -> set[str]:
        ownership_markers = (
            "发布", "推出", "自研", "旗下", "自主研发", "developed", "launched",
            "released", "unveiled", "its ", "'s ", " by ",
        )
        ignored = {
            "ai", "api", "llm", "agent", "agents", "model", "models", "company",
            "corporation", "group", "platform", "product", "products",
        }
        owned: set[str] = set()
        for item in evidence.values():
            item_text = item.text.casefold()
            metadata = (source_metadata or {}).get(item.source_id, {})
            source_title = str(metadata.get("title") or "").casefold()
            source_is_target_context = (
                item.source_type == "official"
                or any(alias in source_title for alias in company_aliases)
            )
            item_is_ownership_context = (
                any(alias in item_text for alias in company_aliases)
                and any(marker in item_text for marker in ownership_markers)
            )
            for clause in re.split(r"[。！？；\n.!?;]", item.text):
                normalized_clause = clause.casefold()
                clause_is_ownership_context = (
                    any(alias in normalized_clause for alias in company_aliases)
                    and any(marker in normalized_clause for marker in ownership_markers)
                )
                if not clause_is_ownership_context and not item_is_ownership_context and not source_is_target_context:
                    continue
                for candidate in re.findall(r"\b[A-Z][A-Za-z0-9.-]{2,}(?:\s+[A-Z][A-Za-z0-9.-]{2,}){0,2}\b", clause):
                    normalized = candidate.casefold().strip(" .-")
                    if (
                        source_is_target_context
                        and not clause_is_ownership_context
                        and not item_is_ownership_context
                        and not re.search(r"(?:^|-)v?\d", normalized)
                    ):
                        continue
                    if normalized in ignored or cls._entity_is_target_owned(candidate, company_aliases, set()):
                        continue
                    owned.add(normalized)
                    for token in re.findall(r"[A-Za-z][A-Za-z0-9.-]{2,}", candidate):
                        normalized_token = token.casefold().strip(" .-")
                        if normalized_token not in ignored:
                            owned.add(normalized_token)
                            parts = [part for part in normalized_token.split("-") if part]
                            if len(parts) >= 3:
                                # Models often abbreviate a product such as
                                # MiMo-V2-TTS to V2-TTS in an entity field.
                                owned.add("-".join(parts[1:]))
        return owned

    @staticmethod
    def _entity_is_target_owned(
        entity: str,
        company_aliases: set[str],
        owned_entity_aliases: set[str],
    ) -> bool:
        normalized = re.sub(r"\s+", " ", entity.casefold()).strip(" ./")
        aliases = company_aliases | owned_entity_aliases
        for alias in aliases:
            normalized_alias = re.sub(r"\s+", " ", alias.casefold()).strip(" ./")
            if len(normalized_alias) < 2:
                continue
            if normalized == normalized_alias:
                return True
            if re.search(r"[\u3400-\u9fff]", normalized_alias) and normalized_alias in normalized:
                return True
            # The model may return a comma/slash-separated entity list (for example
            # "MiMo V2 Pro, Hermes Agent").  A target-owned member makes the whole
            # competitive entity unsafe, even when it is not the only member.
            alias_pattern = re.escape(normalized_alias).replace(r"\-", r"[-\s]")
            if re.search(rf"(?:^|[^a-z0-9]){alias_pattern}(?:$|[^a-z0-9])", normalized):
                return True
            if re.fullmatch(r"[a-z0-9.-]+", normalized_alias) and (
                normalized.startswith(f"{normalized_alias}-")
                or normalized.startswith(f"{normalized_alias} ")
                or normalized.startswith(f"{normalized_alias}v")
            ):
                return True
        return False

    @staticmethod
    def _company_relevance(
        evidence_ids: list[str],
        evidence: dict[str, Evidence],
        source_metadata: dict[str, dict],
        company_aliases: set[str],
    ) -> Literal["direct", "indirect", "none"]:
        for evidence_id in evidence_ids:
            item = evidence.get(evidence_id)
            if not item:
                continue
            if item.source_type == "official":
                return "direct"
            metadata = source_metadata.get(item.source_id, {})
            haystack = f'{metadata.get("title", "")} {item.text}'.casefold()
            if any(alias in haystack for alias in company_aliases):
                return "direct"
        return "none"

    @classmethod
    def _filter_recent_company_anchors(
        cls,
        items: list[dict],
        evidence: dict[str, Evidence],
        source_metadata: dict[str, dict],
        company_aliases: set[str],
    ) -> list[dict]:
        kept: list[dict] = []
        for index, item in enumerate(items):
            relevance = cls._company_relevance(
                list(item.get("evidence_ids", [])), evidence, source_metadata, company_aliases,
            )
            role_relevance = item.get("role_relevance")
            if relevance != "direct":
                logger.warning("company_research_item_dropped %s", json.dumps({
                    "section": "recent_signals",
                    "item_index": index,
                    "field": "evidence_ids",
                    "validation_rule": "missing_company_anchor",
                    "error_type": "GroundingValidationError",
                    "expected_constraint": "direct_target_company_evidence",
                    "action": "item_dropped",
                    "role_relevance": role_relevance,
                    "company_relevance": relevance,
                }, separators=(",", ":")))
                continue
            kept.append(item)
        return kept

    @classmethod
    def _validate_competitive_relation(
        cls,
        item: CompetitiveContextItem,
        refs: list[Evidence],
        company_aliases: set[str],
        item_index: int,
    ) -> None:
        combined = " ".join(ref.text for ref in refs).casefold()
        competitor_tokens = {
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9-]{3,}|[\u3400-\u9fff]{2,}", item.competitor)
            if token.casefold() not in {"公司", "平台", "产品", "company", "platform", "product"}
        }
        if not competitor_tokens or not any(token in combined for token in competitor_tokens):
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="missing_specific_competitor", offending_evidence_ids=item.evidence_ids,
            )
        if not any(alias in combined for alias in company_aliases):
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="missing_comparison_relation", offending_evidence_ids=item.evidence_ids,
            )
        comparison_markers = (
            "对标", "对比", "比较", "竞品", "竞争", "替代", "相比", "区别", "不同",
            "versus", " vs ", "compared", "comparison", "alternative", "competitor",
        )
        if not any(marker in combined for marker in comparison_markers):
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="missing_supported_difference", offending_evidence_ids=item.evidence_ids,
            )

    @classmethod
    def _validate_company_map_item(
        cls,
        item: CompanyMapItem,
        refs: list[Evidence],
        item_index: int,
    ) -> None:
        if item.category in {"customers", "financial_operating_context"} and item.claim_type != "fact":
            raise GroundingValidationError(
                section="company_map", item_index=item_index,
                validation_rule="factual_category_requires_fact", offending_evidence_ids=item.evidence_ids,
            )
        if item.claim_type == "grounded_synthesis":
            if len({ref.evidence_id for ref in refs}) < 2:
                raise GroundingValidationError(
                    section="company_map", item_index=item_index,
                    validation_rule="grounded_synthesis_requires_multiple_evidence",
                    offending_evidence_ids=item.evidence_ids,
                )
            combined = " ".join(ref.text for ref in refs).casefold()
            # Product/platform names and numeric claims are high-risk synthesis
            # components. They must occur in at least one cited evidence record.
            candidates = re.findall(r"\b[A-Z][A-Za-z0-9.-]{2,}\b|\b\d+(?:\.\d+)?%?\b", item.text)
            unsupported = [token for token in candidates if token.casefold() not in combined]
            if unsupported:
                raise GroundingValidationError(
                    section="company_map", item_index=item_index,
                    validation_rule="unsupported_synthesis_component",
                    offending_evidence_ids=item.evidence_ids,
                )

    @staticmethod
    def _competitive_evidence_guidance(
        evidence: dict[str, Evidence],
        company_aliases: set[str],
        owned_entity_aliases: set[str] | None = None,
    ) -> dict[str, dict[str, object]]:
        comparison_markers = (
            "对标", "对比", "比较", "竞品", "竞争", "替代", "相比", "区别", "不同",
            "versus", " vs ", "compare", "comparison", "alternative", "competitor", "rival", "beats",
        )
        guidance = {}
        for evidence_id, item in evidence.items():
            if item.evidence_type != "competitive":
                continue
            text = item.text.casefold()
            has_company_anchor = any(alias in text for alias in company_aliases)
            has_comparison_relation = any(marker in text for marker in comparison_markers)
            has_only_generic_comparison = bool(re.search(r"同(?:级|等)(?:别)?(?:竞品|模型|服务)", text))
            named_entities = []
            for candidate in re.findall(r"\b[A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,2}\b", item.text):
                normalized = candidate.casefold().strip()
                if normalized in {
                    "ai", "api", "mcp", "llm", "agent", "agents", "ai agent", "ai agents",
                    "agent team", "agent os", "claw", "now", "today", "this", "the",
                }:
                    continue
                if normalized.endswith("-"):
                    continue
                if re.search(
                    r"(?:attention|architecture|capability|capabilities|transformer|algorithm)$",
                    normalized,
                ):
                    continue
                if GroundedResearchGenerator._entity_is_target_owned(
                    candidate, company_aliases, owned_entity_aliases or set(),
                ):
                    continue
                if candidate not in named_entities:
                    named_entities.append(candidate)
            guidance[evidence_id] = {
                "candidate_type": (
                    "direct_competitor_candidate"
                    if has_company_anchor and has_comparison_relation and not has_only_generic_comparison
                    else "comparable_reference_candidate"
                ),
                "named_entities": named_entities[:5],
            }
        return guidance

    @classmethod
    def _build_comparable_reference_fallback(
        cls,
        evidence: dict[str, Evidence],
        company_aliases: set[str],
        owned_entity_aliases: set[str] | None = None,
    ) -> dict[str, object] | None:
        guidance = cls._competitive_evidence_guidance(
            evidence, company_aliases, owned_entity_aliases or set(),
        )
        target_items = [
            item for item in evidence.values()
            if item.evidence_type in {"company", "role"}
            and item.source_type in {"user_provided", "ai_inference", "official", "external", "campus"}
        ]
        for evidence_id, entry in guidance.items():
            if entry["candidate_type"] != "comparable_reference_candidate":
                continue
            named_entities = entry.get("named_entities") or []
            if not named_entities:
                continue
            item = evidence[evidence_id]
            dimension = cls._detect_reference_dimension(item.text)
            if not dimension:
                continue
            target_item = next(
                (candidate for candidate in target_items if cls._shared_dimension_supported(dimension, candidate.text.casefold())),
                None,
            )
            if target_item is None:
                continue
            entity = str(named_entities[0])
            reference_point = next(
                (
                    sentence.strip()
                    for sentence in re.split(r"(?<=[。！？.!?])\s*", item.text)
                    if entity.casefold() in sentence.casefold()
                    and cls._shared_dimension_supported(dimension, sentence.casefold())
                ),
                item.text.strip(),
            )[:1_500]
            return {
                "context_type": "comparable_reference",
                "competitor": entity,
                "comparison_dimension": dimension,
                "observed_difference": reference_point,
                "interview_relevance": f"面试时可用这个参考准备{dimension}相关的产品边界与设计取舍。",
                "what_reference_does": reference_point,
                "what_target_role_emphasizes": cls._dimension_relevant_excerpt(
                    target_item.text, dimension,
                ),
                "interview_takeaway": f"可以据此准备{dimension}如何连接模型能力、产品流程和实际场景的问题。",
                "claim_type": "grounded_synthesis",
                "evidence_ids": [evidence_id, target_item.evidence_id],
            }
        return None

    @classmethod
    def _dimension_relevant_excerpt(cls, text: str, dimension: str) -> str:
        segments = [
            segment.strip(" ：:;-\n")
            for segment in re.split(r"(?=\s*\d+[、.])|[。！？;；\n]", text)
            if segment.strip()
        ]
        matching = [segment for segment in segments if cls._shared_dimension_supported(dimension, segment.casefold())]
        return (matching[0] if matching else text)[:600]

    @staticmethod
    def _detect_reference_dimension(text: str) -> str | None:
        normalized = text.casefold()
        dimensions = (
            (("workflow", "工作流", "编排"), "工作流编排"),
            (("multi-agent", "agent team", "多智能体"), "多智能体协作"),
            (("skill", "tool", "mcp", "技能", "工具"), "技能与工具调用"),
            (("knowledge", "知识管理", "知识库", "rag"), "知识管理"),
            (("office", "办公", "协同"), "办公协同"),
            (("deploy", "deployment", "部署", "接入", "集成"), "Agent 部署与模型接入"),
            (("developer", "开发者", "生态"), "开发者生态"),
            (("agent", "智能体"), "Agent 产品能力"),
            (("model", "llm", "大模型", "模型"), "模型能力"),
        )
        return next((label for tokens, label in dimensions if any(token in normalized for token in tokens)), None)

    @classmethod
    def _validate_comparable_reference(
        cls,
        item: CompetitiveContextItem,
        refs: list[Evidence],
        company_aliases: set[str],
        item_index: int,
    ) -> None:
        combined = " ".join(ref.text for ref in refs).casefold()
        reference_refs = [
            ref for ref in refs
            if ref.evidence_type == "competitive" and ref.source_type == "external"
        ]
        target_refs = [
            ref for ref in refs
            if ref.evidence_type in {"company", "role"}
            and ref.source_type in {"user_provided", "ai_inference", "official", "external", "campus"}
        ]
        if not reference_refs:
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="missing_reference_side_evidence", offending_evidence_ids=item.evidence_ids,
            )
        if not target_refs:
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="missing_target_side_evidence", offending_evidence_ids=item.evidence_ids,
            )
        reference_text = " ".join(ref.text for ref in reference_refs).casefold()
        target_text = " ".join(ref.text for ref in target_refs).casefold()
        normalized_entity = item.competitor.casefold().strip()
        entity_tokens = {
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9-]{3,}|[\u3400-\u9fff]{2,}", item.competitor)
            if token.casefold() not in {"公司", "平台", "产品", "company", "platform", "product"}
        }
        is_target_entity = any(
            alias == normalized_entity or alias in normalized_entity
            for alias in company_aliases
            if len(alias) >= 3
        )
        if is_target_entity or not entity_tokens or not any(token in reference_text for token in entity_tokens):
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="missing_specific_reference", offending_evidence_ids=item.evidence_ids,
            )
        if not (
            cls._shared_dimension_supported(item.comparison_dimension, reference_text)
            and cls._shared_dimension_supported(item.comparison_dimension, target_text)
        ):
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="missing_shared_dimension", offending_evidence_ids=item.evidence_ids,
            )
        if not item.what_reference_does or not cls._shared_dimension_supported(item.what_reference_does, reference_text):
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="unsupported_reference_point", offending_evidence_ids=item.evidence_ids,
            )
        if not item.what_target_role_emphasizes or not cls._shared_dimension_supported(
            item.what_target_role_emphasizes, target_text,
        ):
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="unsupported_target_emphasis", offending_evidence_ids=item.evidence_ids,
            )
        if item.claim_type != "grounded_synthesis":
            raise GroundingValidationError(
                section="competitive_context", item_index=item_index,
                validation_rule="bounded_comparison_requires_synthesis", offending_evidence_ids=item.evidence_ids,
            )

    @staticmethod
    def _shared_dimension_supported(value: str, evidence_text: str) -> bool:
        dimension_families = (
            ("agent", "智能体"),
            ("workflow", "工作流", "编排"),
            ("skill", "技能"),
            ("tool", "工具", "mcp"),
            ("knowledge", "知识管理", "知识库", "rag"),
            ("office", "办公", "协同"),
            ("enterprise", "企业服务", "tob"),
            ("developer", "开发者", "生态"),
            ("multi-agent", "多智能体", "agent team"),
            ("model", "模型", "llm", "大模型"),
            ("api", "接口"),
            ("deploy", "deployment", "部署"),
            ("context", "上下文"),
            ("price", "pricing", "定价", "成本"),
        )
        normalized_value = value.casefold()
        return any(
            any(token in normalized_value for token in family)
            and any(token in evidence_text for token in family)
            for family in dimension_families
        )

    @classmethod
    def _preprocess_section_items(
        cls,
        section: str,
        items: list[dict],
        evidence: dict[str, Evidence],
    ) -> tuple[list[dict], list[tuple[int, str]]]:
        kept: list[dict] = []
        dropped: list[tuple[int, str]] = []
        seen_categories: set[str] = set()
        seen_text: set[str] = set()
        seen_sources: list[set[str]] = []
        seen_reverse_themes: set[str] = set()
        for index, item in enumerate(items):
            if section == "recent_signals" and item.get("role_relevance") == "low":
                dropped.append((index, "low_role_relevance"))
                continue
            if section == "likely_interview_focus" and item.get("confidence") == "low":
                dropped.append((index, "low_confidence"))
                continue
            category = item.get("category")
            if section in {"company_map", "role_decoder"} and category in seen_categories:
                dropped.append((index, "duplicate_category"))
                continue
            text_value = str(item.get("title") or item.get("question") or "")
            normalized = re.sub(r"[^\w\u3400-\u9fff]", "", text_value.casefold())
            source_ids = {
                evidence[evidence_id].source_id
                for evidence_id in item.get("evidence_ids", [])
                if evidence_id in evidence
            }
            if section == "recent_signals":
                tokens = cls._event_tokens(text_value)
                duplicate = normalized in seen_text
                if not duplicate:
                    for prior, prior_sources in zip(kept, seen_sources):
                        prior_text = str(prior.get("title") or "").casefold()
                        prior_tokens = cls._event_tokens(prior_text)
                        union = tokens | prior_tokens
                        overlap = len(tokens & prior_tokens) / len(union) if union else 0
                        if overlap >= 0.75 or (source_ids & prior_sources and overlap >= 0.45):
                            duplicate = True
                            break
                if duplicate:
                    dropped.append((index, "duplicate_event"))
                    continue
            if section == "reverse_questions":
                theme = cls._reverse_question_theme(text_value)
                if normalized in seen_text or (theme and theme in seen_reverse_themes):
                    dropped.append((index, "duplicate_question"))
                    continue
                if theme:
                    seen_reverse_themes.add(theme)
            if category:
                seen_categories.add(category)
            if normalized:
                seen_text.add(normalized)
            seen_sources.append(source_ids)
            kept.append(item)
        if section in {"company_map", "role_decoder"}:
            priorities = {
                "company_positioning": 0, "core_business": 1, "customers": 2, "current_focus": 3,
                "financial_operating_context": 4, "role_goal": 0, "core_responsibilities": 1,
                "business_scenarios": 2, "key_capabilities": 3, "why_role_exists": 4,
            }
            kept.sort(key=lambda item: priorities.get(str(item.get("category")), 99))
        return kept, dropped

    @staticmethod
    def _event_tokens(text: str) -> set[str]:
        normalized = text.casefold()
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        for chunk in re.findall(r"[\u3400-\u9fff]+", normalized):
            tokens.update(chunk[index:index + 2] for index in range(max(len(chunk) - 1, 1)))
        return tokens

    @staticmethod
    def _reverse_question_theme(question: str) -> str | None:
        themes = {
            "onboarding": ("前三个月", "前3个月", "入职初期", "新人", "刚加入", "刚开始", "先负责", "从哪类项目"),
            "team_priority": ("团队目前", "团队当前", "最优先", "重点推进", "最希望优先"),
            "collaboration": ("怎么分工", "如何分工", "协作方式", "通常怎么协作", "通常如何协作"),
            "success": ("做得好不好", "成功标准", "工作效果", "结果指标", "目标或预期"),
            "challenge": ("主要挑战", "最大挑战", "最大的业务挑战", "最需要解决的问题"),
        }
        return next((theme for theme, markers in themes.items() if any(marker in question for marker in markers)), None)

    @staticmethod
    def _meets_section_minimum(section: str, items: list[dict]) -> bool:
        minimums = {
            "company_map": 2,
            "role_decoder": 3,
            "recent_signals": 2,
            "competitive_context": 1,
            "likely_interview_focus": 2,
            "why_company_why_role_60s": 1,
            "reverse_questions": 2,
        }
        if section == "recent_signals" and len(items) == 1:
            return items[0].get("role_relevance") == "high"
        return len(items) >= minimums[section]

    @staticmethod
    def _log_item_dropped(
        section: str,
        item_index: int,
        validation_rule: str,
        remaining: int,
        *,
        field: object | None = None,
        error_type: object | None = None,
        expected_constraint: object | None = None,
    ) -> None:
        if section == "recent_signals" and field is None:
            field = {
                "low_role_relevance": "role_relevance",
                "duplicate_event": "title",
                "missing_company_anchor": "evidence_ids",
            }.get(validation_rule)
        if section == "recent_signals" and error_type is None:
            error_type = "ValidationError"
        if section == "recent_signals" and expected_constraint is None:
            expected_constraint = {
                "low_role_relevance": "high_or_medium_role_relevance",
                "duplicate_event": "unique_recent_event",
                "missing_company_anchor": "direct_target_company_evidence",
            }.get(validation_rule)
        payload = {
            "section": section,
            "item_index": item_index,
            "validation_rule": validation_rule,
            "action": "item_dropped",
            "remaining_item_count": remaining,
        }
        if section in {"recent_signals", "competitive_context", "why_company_why_role_60s"}:
            payload.update({
                "field": field,
                "error_type": error_type,
                "expected_constraint": expected_constraint,
            })
        logger.warning("company_research_item_dropped %s", json.dumps(payload, separators=(",", ":")))

    @staticmethod
    def _log_below_minimum(section: str, remaining: int) -> None:
        logger.warning("company_research_section_degraded %s", json.dumps({
            "generation_status": "partial",
            "section": section,
            "reason": "below_minimum_valid_items",
            "remaining_item_count": remaining,
        }, separators=(",", ":")))

    @staticmethod
    def _log_fallback(status: str, exc: Exception) -> None:
        validation_fields = {}
        if isinstance(exc, GroundingValidationError):
            validation_fields = {
                "validation_stage": exc.validation_stage,
                "section": exc.section,
                "item_index": exc.item_index,
                "validation_rule": exc.validation_rule,
                "offending_evidence_ids": exc.offending_evidence_ids,
                "offending_evidence_metadata": exc.offending_evidence_metadata,
            }
        logger.warning(
            "company_research_generation_fallback %s",
            json.dumps({
                "status": status,
                "error_type": type(exc).__name__,
                **validation_fields,
            }, separators=(",", ":")),
        )

    @staticmethod
    def _log_section_degraded(section: str, exc: Exception) -> None:
        fields = {
            "generation_status": "partial",
            "section": section,
            "error_type": type(exc).__name__,
        }
        if isinstance(exc, GroundingValidationError):
            fields.update({
                "validation_stage": exc.validation_stage,
                "item_index": exc.item_index,
                "validation_rule": exc.validation_rule,
                "offending_evidence_ids": exc.offending_evidence_ids,
                "offending_evidence_metadata": exc.offending_evidence_metadata,
            })
        logger.warning(
            "company_research_section_degraded %s",
            json.dumps(fields, separators=(",", ":")),
        )
