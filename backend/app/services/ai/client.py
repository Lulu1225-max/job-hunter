from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeVar

from openai import OpenAI
from openai import APIError
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.runtime_logging import get_server_logger


SchemaT = TypeVar("SchemaT", bound=BaseModel)
logger = get_server_logger()
MIN_RESPONSES_OUTPUT_TOKENS = 16


def _safe_identifier(value: object | None) -> str | None:
    if value is None: return None
    text = str(value)[:100]
    return text if re.fullmatch(r"[A-Za-z0-9_.-]+", text) else "redacted"


def _error_details(exc: Exception, flow: str, question_type: str | None) -> dict:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else {}
    code = getattr(exc, "code", None) or (error.get("code") if isinstance(error, dict) else None)
    error_type = getattr(exc, "type", None) or (error.get("type") if isinstance(error, dict) else None)
    if status == 400: safe_message = "OpenAI rejected the request"
    elif status in (401, 403): safe_message = "OpenAI authentication or permission failed"
    elif status == 429: safe_message = "OpenAI rate limit exceeded"
    elif isinstance(status, int) and status >= 500: safe_message = "OpenAI service error"
    elif status: safe_message = "OpenAI API request failed"
    elif isinstance(exc, RuntimeError) and "configured" in str(exc).casefold(): safe_message = "OpenAI client is not configured"
    else: safe_message = "OpenAI request failed before receiving a response"
    return {
        "event": "openai_call_failed",
        "flow": _safe_identifier(flow) or "unknown",
        "question_type": _safe_identifier(question_type) if question_type else None,
        "exception_type": type(exc).__name__,
        "status_code": status if isinstance(status, int) else None,
        "openai_error_code": _safe_identifier(code),
        "openai_error_type": _safe_identifier(error_type),
        "safe_message": safe_message,
    }


def _log_openai_failure(exc: Exception, flow: str, question_type: str | None = None) -> None:
    # Do not log exc, traceback, request payload, prompt, headers, or SDK response body.
    logger.error("openai_call_failed %s", json.dumps(_error_details(exc, flow, question_type), separators=(",", ":")))


def _schema_validation_diagnostic(exc: ValidationError) -> dict:
    errors = exc.errors(include_url=False, include_context=True, include_input=False)
    if not errors:
        return {
            "section": None,
            "field": None,
            "item_index": None,
            "validation_rule": "unknown",
            "error_type": "ValidationError",
            "expected_constraint": None,
        }
    error = errors[0]
    location = error.get("loc", ())
    safe_location = [part for part in location if isinstance(part, (str, int))]
    string_location = [part for part in safe_location if isinstance(part, str) and part != "items"]
    section = string_location[0] if string_location else None
    field = string_location[-1] if string_location else None
    item_index = next((part for part in safe_location if isinstance(part, int)), None)
    validation_rule = _safe_identifier(error.get("type")) or "unknown"
    context = error.get("ctx") if isinstance(error.get("ctx"), dict) else {}
    safe_validator_rules = (
        ("role_goal must be inference", "wrong_claim_type", "claim_type", "role_goal_requires_inference"),
        ("core_responsibilities must be fact", "wrong_claim_type", "claim_type", "core_responsibilities_require_fact"),
        ("business_scenarios must be inference", "wrong_claim_type", "claim_type", "business_scenarios_require_inference"),
        ("key_capabilities must be fact", "wrong_claim_type", "claim_type", "key_capabilities_require_fact"),
        ("why_role_exists must be inference", "wrong_claim_type", "claim_type", "why_role_exists_requires_inference"),
        ("role decoder cannot contain candidate-fit assessment", "candidate_fit_forbidden", "text", "no_candidate_fit"),
        ("business scenarios must name concrete supported scenarios", "business_scenario_too_generic", "text", "concrete_business_scenario_required"),
        ("key capabilities cannot consist only of generic soft skills", "generic_soft_skills_only", "text", "role_specific_capability_required"),
        ("why-company answer contains corporate cliches", "corporate_cliche", "text", "no_corporate_cliches"),
        ("why-company answer must include a clear company reason", "missing_company_reason", "text", "company_reason_required"),
        ("why-company answer must include a clear role reason", "missing_role_reason", "text", "role_reason_required"),
        ("why-company answer must include personal direction motivation without candidate fit", "missing_personal_motivation", "text", "personal_motivation_required"),
        ("company reason cannot rely only on financial data", "financial_only_company_reason", "text", "non_financial_company_context_required"),
        ("reverse question is not appropriate for a junior candidate", "unsupported_question_type", "question", "junior_appropriate_question_required"),
        ("candidate methodology questions belong in likely interview focus", "methodology_question", "question", "question_must_ask_about_team_reality"),
        ("reverse question is overly technical diligence for a junior candidate", "senior_due_diligence", "question", "no_expert_due_diligence"),
        ("reverse question must be phrased as a question", "not_a_question", "question", "question_mark_required"),
        ("reverse question rationale must explain the specific information gained", "vague_rationale", "rationale", "specific_information_gain_required"),
        ("reverse question rationale lacks a concrete learning objective", "vague_rationale", "rationale", "concrete_learning_objective_required"),
        ("reverse questions cannot contain candidate-fit assessment", "candidate_fit_material", "question_or_rationale", "no_candidate_fit"),
        ("reverse questions cannot be duplicated", "duplicate_question", "question", "unique_questions_required"),
        ("reverse questions cannot repeat the same information need", "duplicate_question", "question", "distinct_information_needs_required"),
        ("recent signal interview relevance must explain a concrete role or interview impact", "vague_interview_relevance", "why_it_matters_for_interview", "concrete_interview_impact_required"),
        ("recent signal interview relevance lacks a concrete role or interview connection", "vague_interview_relevance", "why_it_matters_for_interview", "role_or_interview_connection_required"),
        ("competitive context requires a specifically named company, product, or platform", "missing_specific_entity", "competitor", "concrete_company_product_or_platform"),
        ("competitive context requires a concrete comparison dimension", "invalid_comparison_dimension", "comparison_dimension", "concrete_shared_comparison_dimension"),
        ("competitive context requires a concrete evidence-supported difference", "unsupported_comparison_claim", "observed_difference", "evidence_supported_non_superiority_comparison"),
        ("competitive comparison contains unsupported superiority claim", "unsupported_comparison_claim", "observed_difference", "evidence_supported_non_superiority_comparison"),
        ("comparable reference requires an external capability description", "missing_reference_description", "what_reference_does", "evidence_grounded_external_capability"),
        ("comparable reference requires a target-side emphasis", "missing_target_emphasis", "what_target_role_emphasizes", "target_company_role_or_jd_emphasis"),
        ("comparable reference requires a concrete interview takeaway", "vague_interview_takeaway", "interview_takeaway", "concrete_interview_usefulness"),
        ("competitive context requires a concrete interview impact", "vague_interview_takeaway", "interview_relevance", "concrete_interview_usefulness"),
        ("competitive context interview relevance lacks a role or product connection", "vague_interview_takeaway", "interview_relevance", "role_or_product_specific_interview_usefulness"),
    )
    validator_error = str(context.get("error", ""))
    safe_validator_match = next((rule for rule in safe_validator_rules if rule[0] in validator_error), None)
    if safe_validator_match:
        _, validation_rule, field, expected_constraint = safe_validator_match
    else:
        expected_constraint = None
    for key in ("min_length", "max_length", "min_items", "max_items"):
        value = context.get(key)
        if isinstance(value, int):
            expected_constraint = f"{key}={value}"
            break
    if expected_constraint is None:
        expected_constraint = {
            "missing": "required_field",
            "literal_error": "allowed_literal_value",
            "extra_forbidden": "no_extra_fields",
            "value_error": "schema_validator_rule",
        }.get(validation_rule)
    if section == "recent_signals":
        recent_field_rules = {
            ("title", "string_too_short"): ("missing_title", "non_empty_title"),
            ("why_it_matters_for_interview", "string_too_short"): ("missing_interview_relevance", "non_empty_interview_relevance"),
            ("role_relevance", "literal_error"): ("invalid_role_relevance", "high_or_medium_or_low"),
            ("evidence_ids", "missing"): ("unsupported_evidence", "section_allowed_evidence_ids"),
            ("evidence_ids", "too_short"): ("unsupported_evidence", "at_least_one_allowed_evidence_id"),
            ("evidence_ids", "literal_error"): ("unsupported_evidence", "section_allowed_evidence_ids"),
            ("date", "string_too_long"): ("invalid_date_metadata", "backend_derived_source_date"),
        }
        mapped = recent_field_rules.get((field, validation_rule))
        if mapped:
            validation_rule, expected_constraint = mapped
        elif validation_rule not in {
            "vague_interview_relevance",
            "missing_company_anchor",
            "invalid_date_metadata",
            "duplicate_signal",
        }:
            validation_rule, expected_constraint = "malformed_item", "recent_signal_item_contract"
    if section == "competitive_context":
        competitive_field_rules = {
            ("context_type", "literal_error"): ("invalid_context_type", "direct_competitor_or_comparable_reference"),
            ("context_type", "missing"): ("invalid_context_type", "direct_competitor_or_comparable_reference"),
            ("competitor", "missing"): ("missing_specific_entity", "concrete_company_product_or_platform"),
            ("competitor", "string_too_short"): ("missing_specific_entity", "concrete_company_product_or_platform"),
            ("comparison_dimension", "missing"): ("invalid_comparison_dimension", "concrete_shared_comparison_dimension"),
            ("comparison_dimension", "string_too_short"): ("invalid_comparison_dimension", "concrete_shared_comparison_dimension"),
            ("what_reference_does", "missing"): ("missing_reference_description", "evidence_grounded_external_capability"),
            ("what_reference_does", "string_too_short"): ("missing_reference_description", "evidence_grounded_external_capability"),
            ("what_target_role_emphasizes", "missing"): ("missing_target_emphasis", "target_company_role_or_jd_emphasis"),
            ("what_target_role_emphasizes", "string_too_short"): ("missing_target_emphasis", "target_company_role_or_jd_emphasis"),
            ("interview_takeaway", "missing"): ("vague_interview_takeaway", "concrete_interview_usefulness"),
            ("interview_takeaway", "string_too_short"): ("vague_interview_takeaway", "concrete_interview_usefulness"),
            ("interview_relevance", "missing"): ("vague_interview_takeaway", "concrete_interview_usefulness"),
            ("interview_relevance", "string_too_short"): ("vague_interview_takeaway", "concrete_interview_usefulness"),
            ("observed_difference", "missing"): ("unsupported_comparison_claim", "evidence_supported_non_superiority_comparison"),
            ("observed_difference", "string_too_short"): ("unsupported_comparison_claim", "evidence_supported_non_superiority_comparison"),
            ("evidence_ids", "literal_error"): ("invalid_evidence_alias", "section_candidate_citation_alias"),
            ("evidence_ids", "list_type"): ("malformed_evidence_ids", "single_alias_list"),
            ("evidence_ids", "too_short"): ("malformed_evidence_ids", "at_least_one_evidence_id"),
            ("evidence_ids", "too_long"): ("malformed_evidence_ids", "bounded_evidence_id_list"),
        }
        mapped = competitive_field_rules.get((field, validation_rule))
        if mapped:
            validation_rule, expected_constraint = mapped
        elif validation_rule not in {
            "invalid_context_type", "missing_specific_entity", "invalid_comparison_dimension",
            "missing_reference_description", "missing_target_emphasis", "vague_interview_takeaway",
            "unsupported_comparison_claim", "invalid_evidence_alias", "malformed_evidence_ids",
            "missing_reference_alias", "missing_target_alias", "alias_expansion_failed",
        }:
            validation_rule, expected_constraint = "malformed_item", "competitive_context_item_contract"
    if section == "why_company_why_role_60s":
        if field == "text" and validation_rule in {"string_too_short", "string_too_long"}:
            validation_rule = "length_violation"
        elif field == "evidence_ids" and validation_rule in {"missing", "too_short", "literal_error"}:
            validation_rule, expected_constraint = "unsupported_evidence", "company_and_role_allowed_evidence"
        elif validation_rule not in {
            "missing_company_reason", "missing_role_reason", "missing_personal_motivation",
            "corporate_cliche", "candidate_fit_material", "length_violation", "unsupported_evidence",
        }:
            validation_rule, expected_constraint = "malformed_item", "why_company_role_item_contract"
    return {
        "section": _safe_identifier(section) if section else None,
        "field": _safe_identifier(field) if field else None,
        "item_index": item_index,
        "validation_rule": validation_rule,
        "error_type": "ValidationError",
        "expected_constraint": expected_constraint,
    }


def log_post_openai_stage(stage: str, flow: str, question_type: str | None = None,
                          exc: Exception | None = None, parsed_output_present: bool | None = None) -> None:
    fields = {
        "flow": _safe_identifier(flow) or "unknown",
        "question_type": _safe_identifier(question_type) if question_type else None,
        "exception_type": type(exc).__name__ if exc else None,
        "stage": _safe_identifier(stage) or "unknown",
        "parsed_output_present": parsed_output_present,
    }
    if stage == "schema_validation_failed" and isinstance(exc, ValidationError):
        fields.update(_schema_validation_diagnostic(exc))
    # Never include exception text, payload, prompt, response body, or parsed output.
    logger.warning("openai_postprocess %s", json.dumps(fields, separators=(",", ":")))


class AIClient:
    def check_responses_api(self) -> None:
        """Minimal authenticated connectivity check; response content is discarded."""
        try:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            OpenAI(api_key=settings.openai_api_key).responses.create(
                model=settings.openai_model,
                input="Reply with OK only.",
                max_output_tokens=MIN_RESPONSES_OUTPUT_TOKENS,
            )
        except Exception as exc:
            _log_openai_failure(exc, "openai_connectivity_diagnostic")
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        normalized = [text[: settings.embedding_max_characters] for text in texts]
        response = OpenAI(api_key=settings.openai_api_key).embeddings.create(
            model=settings.openai_embedding_model,
            input=normalized,
            dimensions=settings.openai_embedding_dimension,
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def get_embedding(self, text: str) -> list[float]:
        return self.get_embeddings([text])[0]

    def structured_completion(
        self,
        *,
        prompt_name: str,
        schema: type[SchemaT],
        payload: dict,
        diagnostic_context: dict[str, str] | None = None,
    ) -> SchemaT:
        context = diagnostic_context or {}
        flow = context.get("flow", prompt_name)
        try:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            prompt_path = Path(__file__).resolve().parents[2] / "prompts" / f"{prompt_name}.txt"
            instructions = prompt_path.read_text(encoding="utf-8")
            try:
                response = OpenAI(api_key=settings.openai_api_key).responses.parse(
                    model=settings.openai_model,
                    instructions=instructions,
                    input=json.dumps(payload, ensure_ascii=False),
                    text_format=schema,
                )
            except ValidationError as exc:
                log_post_openai_stage("schema_validation_failed", flow, context.get("question_type"), exc, False)
                setattr(exc, "_openai_diagnostic_logged", True)
                raise
            except Exception as exc:
                # SDK HTTP failures belong to the existing openai_call_failed
                # diagnostic. Tests and compatible clients may expose an HTTP
                # status without inheriting from the installed SDK's APIError.
                if isinstance(exc, APIError) or getattr(exc, "status_code", None) is not None:
                    raise
                log_post_openai_stage("structured_parse_failed", flow, context.get("question_type"), exc, False)
                setattr(exc, "_openai_diagnostic_logged", True)
                raise
            log_post_openai_stage("openai_http_success", flow, context.get("question_type"), parsed_output_present=response.output_parsed is not None)
            if response.output_parsed is None:
                log_post_openai_stage("output_parsed_missing", flow, context.get("question_type"), parsed_output_present=False)
                exc = RuntimeError("OpenAI did not return a structured result")
                setattr(exc, "_openai_diagnostic_logged", True)
                raise exc
            return response.output_parsed
        except Exception as exc:
            if not getattr(exc, "_openai_diagnostic_logged", False):
                _log_openai_failure(exc, flow, context.get("question_type"))
            raise


ai_client = AIClient()
