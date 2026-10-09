from __future__ import annotations

from hashlib import sha256
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from uuid import UUID
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.repositories.database import company_profiles_repo, jobs_repo
from app.core.config import settings
from app.core.runtime_logging import get_server_logger
from app.skills.company_role_research.evidence import EvidenceExtractor
from app.skills.company_role_research.competitive_discovery import (
    CompetitiveCandidateMetadata,
    candidate_entity_key,
    infer_competitive_dimensions,
    shared_dimensions,
)
from app.skills.company_role_research.fetcher import SourceFetcher
from app.skills.company_role_research.generator import GroundedResearchGenerator, unavailable_report
from app.skills.company_role_research.profile import (
    COMPANY_PROFILE_TTL_DAYS,
    CompanyProfileGenerator,
    company_profile_generator,
    normalize_company_name,
)
from app.skills.company_role_research.profile_research import (
    MAX_FETCH_PAGES,
    MAX_FETCH_PER_ROUND,
    MAX_SEARCH_ROUNDS,
    assess_profile_coverage,
    extended_coverage_sufficient,
    plan_profile_search,
)
from app.skills.company_role_research.providers import (
    CompanyResearchProvider,
    EmptyCompanyResearchProvider,
    create_company_research_provider,
)

from app.skills.company_role_research.schemas import (
    CompanyRoleResearchInput,
    CompanyRoleResearchOutput,
    CompanyKnowledge,
    CompanyKnowledgeSource,
    Evidence,
    FetchedSource,
    GenerationStatus,
    GroundedResearchGeneration,
    InterviewReferenceFallbacks,
    SourceMetadata,
    WebSearchSource,
)


logger = get_server_logger()


class CompanyRoleResearchSkill:
    """Orchestrates grounded company/role research without candidate-fit logic."""

    def __init__(
        self,
        provider: CompanyResearchProvider | None = None,
        *,
        fetcher: SourceFetcher | None = None,
        evidence_extractor: EvidenceExtractor | None = None,
        generator: GroundedResearchGenerator | None = None,
        profile_generator: CompanyProfileGenerator | None = None,
        use_cached_profile: bool = False,
    ) -> None:
        self.provider = provider or EmptyCompanyResearchProvider()
        self.fetcher = fetcher or SourceFetcher()
        self.evidence_extractor = evidence_extractor or EvidenceExtractor()
        self.generator = generator or GroundedResearchGenerator()
        self.profile_generator = profile_generator or company_profile_generator
        self.use_cached_profile = use_cached_profile

    def _run_cached_profile(
        self,
        db: Session,
        request: CompanyRoleResearchInput,
        *,
        force_profile_refresh: bool,
    ) -> CompanyRoleResearchOutput:
        """Default low-cost path: one cached company profile plus one JD-specific brief call."""
        normalized_name = normalize_company_name(request.company_name)
        profile = company_profiles_repo.get(db, normalized_name)
        profile_has_provenance = bool(
            profile and (getattr(profile, "source_provenance", None) or {}).get("retrieval_attempted")
        )
        cache_hit = profile is not None and not force_profile_refresh and profile_has_provenance
        if profile is None or force_profile_refresh or not profile_has_provenance:
            (
                fetched,
                successful_sources,
                public_evidence,
                source_category_by_id,
                research_diagnostics,
            ) = self._research_company_profile(request)
            source_ids = [item.source_id for item in successful_sources]
            customer_markers = ("customer", "consumer", "client", "user", "用户", "客户", "消费者", "开发者")
            customer_source_ids = list(dict.fromkeys(
                item["source_id"] for item in public_evidence
                if any(marker in item["text"].casefold() for marker in customer_markers)
            ))
            source_provenance = {
                "retrieval_attempted": True,
                "retrieval_diagnostics": {
                    "search_count": research_diagnostics["search_count"],
                    "fetch_attempt_count": len(fetched),
                    "fetch_success_count": len(successful_sources),
                    "extracted_evidence_count": len(public_evidence),
                    "stop_reason": research_diagnostics["stop_reason"],
                },
                "research_rounds": research_diagnostics["rounds"],
                "coverage": research_diagnostics["coverage"],
                "sources": [
                    {
                        "source_id": item.source_id,
                        "title": item.title,
                        "url": item.url,
                        "source_type": item.source_type,
                        "published_at": item.published_at,
                        "category": source_category_by_id.get(item.source_id),
                    }
                    for item in successful_sources
                ],
                "fields": {
                    "company_positioning": [
                        source_id for source_id in source_ids
                        if source_category_by_id.get(source_id) in {"overview", "investor"}
                    ] or source_ids,
                    "core_business": source_ids,
                    "key_brands_and_products": [
                        source_id for source_id in source_ids
                        if source_category_by_id.get(source_id) in {"overview", "platform_ecosystem", "strategic_product"}
                    ],
                    "customer_and_market": customer_source_ids,
                },
            }
            try:
                draft = self.profile_generator.generate(request.company_name, public_evidence=public_evidence[:24])
            except TypeError:  # Compatibility for injected test/profile generators.
                draft = self.profile_generator.generate(request.company_name)
            try:
                values = self.profile_generator.persistence_values(
                    request.company_name,
                    draft,
                    source_provenance=source_provenance,
                )
            except TypeError:
                values = self.profile_generator.persistence_values(request.company_name, draft)
                values["source_provenance"] = source_provenance
            profile = company_profiles_repo.upsert(
                db,
                normalized_name,
                values,
            )
            db.commit()
            db.refresh(profile)

        generated_at = profile.generated_at
        comparable_now = datetime.now(timezone.utc)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        is_stale = comparable_now - generated_at >= timedelta(days=COMPANY_PROFILE_TTL_DAYS)

        source_id = f"company_profile:{normalized_name}"
        evidence: list[Evidence] = []

        def add_company_evidence(label: str, value: str) -> None:
            if value.strip():
                evidence.append(Evidence(
                    evidence_id=f"profile_{label}_{sha256(value.encode('utf-8')).hexdigest()[:12]}",
                    source_id=source_id,
                    source_type="ai_inference",
                    evidence_type="company",
                    text=value.strip(),
                ))

        add_company_evidence("positioning", profile.positioning)
        for label, values in (
            ("business", profile.business_lines),
            ("brands", profile.key_brands),
            ("products", profile.key_products),
            ("customers", profile.customer_groups),
            ("focus", profile.strategic_focus),
        ):
            if values:
                add_company_evidence(label, "；".join(values))
        if request.saved_jd:
            evidence.append(Evidence(
                evidence_id=f"jd_{sha256(request.saved_jd.encode('utf-8')).hexdigest()[:12]}",
                source_id="saved_job_description",
                source_type="user_provided",
                evidence_type="role",
                text=request.saved_jd,
            ))

        outcome = self.generator.generate(
            company_name=request.company_name,
            job_title=request.job_title,
            saved_jd=request.saved_jd,
            evidence=evidence,
            fetched_sources=[],
            company_profile_context={
                "positioning": profile.positioning,
                "business_lines": list(profile.business_lines or []),
                "key_brands": list(profile.key_brands or []),
                "key_products": list(profile.key_products or []),
                "customer_groups": list(profile.customer_groups or []),
                "strategic_focus": list(profile.strategic_focus or []),
            },
        )
        unavailable = unavailable_report()
        knowledge_report = outcome.report.model_copy(update={
            "recent_signals": unavailable.recent_signals,
            "competitive_context": unavailable.competitive_context,
            "likely_interview_focus": unavailable.likely_interview_focus,
            "why_company_why_role_60s": unavailable.why_company_why_role_60s,
            "reverse_questions": unavailable.reverse_questions,
        })
        comparable_candidates = [
            {
                "entity": item.get("entity_name"),
                "reference_type": item.get("reference_type", "comparable_product"),
                "shared_dimensions": [item.get("shared_dimension")],
                "why_relevant": item.get("why_relevant"),
                "interview_angle": item.get("interview_angle"),
            }
            for item in (profile.comparable_products or [])
        ]
        company_knowledge = self._build_company_knowledge(
            profile,
            request,
            generated_role_products=outcome.role_relevant_products,
        )
        provenance = getattr(profile, "source_provenance", None) or {}
        knowledge_sources = [CompanyKnowledgeSource(**item) for item in provenance.get("sources", [])]
        knowledge_source_ids = {
            key: list(dict.fromkeys(value))
            for key, value in provenance.get("fields", {}).items()
            if isinstance(value, list)
        }
        return self._compose(
            request,
            [],
            [],
            evidence,
            knowledge_report,
            outcome.status,
            competitive_reference_candidates=comparable_candidates,
            watch_topics=list(profile.strategic_focus or []),
            profile_generated_at=profile.generated_at,
            profile_refreshed_at=profile.refreshed_at,
            profile_is_stale=is_stale,
            profile_cache_hit=cache_hit,
            company_knowledge=company_knowledge,
            company_knowledge_source_ids=knowledge_source_ids,
            company_knowledge_sources=knowledge_sources,
            include_interview_answer_fallback=False,
            build_interview_references=False,
        )

    def _research_company_profile(
        self,
        request: CompanyRoleResearchInput,
    ) -> tuple[list[FetchedSource], list[FetchedSource], list[dict[str, str]], dict[str, str], dict[str, Any]]:
        """Run a deterministic, budgeted search/fetch/evidence loop for profile refreshes."""
        fetched: list[FetchedSource] = []
        successful: list[FetchedSource] = []
        public_evidence: list[dict[str, str]] = []
        source_category_by_id: dict[str, str] = {}
        seen_urls: set[str] = set()
        seen_evidence: set[tuple[str, str]] = set()
        rounds: list[dict[str, Any]] = []
        search_count = 0
        stop_reason = "max_search_rounds"
        search_profile = getattr(self.provider, "search_company_profile", None)

        for round_index in range(1, MAX_SEARCH_ROUNDS + 1):
            coverage_before = assess_profile_coverage(
                public_evidence,
                job_title=request.job_title,
                saved_jd=request.saved_jd,
            )
            if extended_coverage_sufficient(
                coverage_before,
                has_role_context=bool(request.job_title or request.saved_jd),
            ):
                stop_reason = "coverage_sufficient"
                break
            if len(fetched) >= MAX_FETCH_PAGES:
                stop_reason = "max_fetch_pages"
                break

            plan = plan_profile_search(
                request.company_name,
                job_title=request.job_title,
                saved_jd=request.saved_jd,
                coverage=coverage_before,
            )
            if not plan.search_needed:
                stop_reason = "planner_low_marginal_value"
                break

            search_official = getattr(self.provider, "search_company_official", None)
            if round_index == 1 and callable(search_official):
                candidates = search_official(request.company_name)
                pool_getter = getattr(self.provider, "get_official_source_pool", None)
                if callable(pool_getter):
                    candidates = pool_getter(request.company_name) or candidates
            elif callable(search_profile):
                candidates = search_profile(request.company_name, plan.search_query)
            else:
                stop_reason = "search_provider_exhausted"
                break
            search_count += 1

            candidates = self._profile_research_candidates(candidates)
            remaining_fetches = MAX_FETCH_PAGES - len(fetched)
            selected = self._select_profile_round_sources(
                candidates,
                missing_dimensions=plan.missing_dimensions,
                seen_urls=seen_urls,
                limit=min(MAX_FETCH_PER_ROUND, remaining_fetches),
            )
            round_new_evidence = 0
            round_fetch_success = 0
            for source in selected:
                seen_urls.add(source.url.rstrip("/"))
                result = self.fetcher.fetch_source(source)
                fetched.append(result)
                if result.fetch_status != "success":
                    continue
                successful.append(result)
                round_fetch_success += 1
                category = self._company_profile_source_category(source)
                source_category_by_id[result.source_id] = category
                for item in self.evidence_extractor.extract(
                    result,
                    company_name=request.company_name,
                    job_title=request.job_title,
                ):
                    if item.evidence_type != "company":
                        continue
                    key = (item.source_id, re.sub(r"\s+", " ", item.text).casefold().strip())
                    if key in seen_evidence:
                        continue
                    seen_evidence.add(key)
                    public_evidence.append({
                        "source_id": item.source_id,
                        "text": item.text,
                        "source_category": category,
                    })
                    round_new_evidence += 1

            coverage_after = assess_profile_coverage(
                public_evidence,
                job_title=request.job_title,
                saved_jd=request.saved_jd,
            )
            round_diagnostic = {
                "round_index": round_index,
                "current_missing_dimensions": plan.missing_dimensions,
                "search_query": plan.search_query,
                "preferred_source_types": plan.preferred_source_types,
                "reason": plan.reason,
                "selected_sources": [source.url for source in selected],
                "fetch_success_count": round_fetch_success,
                "new_evidence_count": round_new_evidence,
                "coverage_after": coverage_after,
            }
            rounds.append(round_diagnostic)
            logger.warning(
                "company_profile_research_round %s",
                json.dumps(round_diagnostic, ensure_ascii=False, separators=(",", ":")),
            )
            if round_new_evidence == 0:
                stop_reason = "no_new_evidence"
                break
            if extended_coverage_sufficient(
                coverage_after,
                has_role_context=bool(request.job_title or request.saved_jd),
            ):
                stop_reason = "coverage_sufficient"
                break
            if len(fetched) >= MAX_FETCH_PAGES:
                stop_reason = "max_fetch_pages"
                break
        else:
            coverage_after = assess_profile_coverage(
                public_evidence,
                job_title=request.job_title,
                saved_jd=request.saved_jd,
            )

        final_coverage = assess_profile_coverage(
            public_evidence,
            job_title=request.job_title,
            saved_jd=request.saved_jd,
        )
        logger.warning("company_profile_research_complete %s", json.dumps({
            "search_count": search_count,
            "fetch_attempt_count": len(fetched),
            "fetch_success_count": len(successful),
            "new_evidence_count": len(public_evidence),
            "stop_reason": stop_reason,
            "coverage": final_coverage,
        }, ensure_ascii=False, separators=(",", ":")))
        return fetched, successful, public_evidence, source_category_by_id, {
            "search_count": search_count,
            "rounds": rounds,
            "stop_reason": stop_reason,
            "coverage": final_coverage,
        }

    @staticmethod
    def _build_company_knowledge(
        profile: Any,
        request: CompanyRoleResearchInput,
        *,
        generated_role_products: list[Any] | None = None,
    ) -> CompanyKnowledge:
        """Combine cached profile facts with JD-specific products generated in the existing research call."""
        role_products = list(generated_role_products or [])
        comparable = [
            {
                "entity_name": item.get("entity_name"),
                "reference_type": item.get("reference_type", "comparable_product"),
                "why_relevant": item.get("why_relevant"),
                "comparison_dimensions": [
                    value.strip() for value in re.split(r"[、,，/]", str(item.get("shared_dimension") or ""))
                    if value.strip()
                ] or ["产品定位与使用场景"],
            }
            for item in (profile.comparable_products or [])
        ]
        return CompanyKnowledge(
            company_positioning=profile.positioning,
            core_business=list(profile.business_lines or []),
            key_brands_and_products=list(dict.fromkeys([*(profile.key_brands or []), *(profile.key_products or [])])),
            customer_and_market=list(profile.customer_groups or []),
            role_relevant_products_and_scenarios=role_products,
            comparable_products=comparable,
        )

    def run(self, db: Session, user_id: UUID, application: Any, *, force_profile_refresh: bool = False) -> CompanyRoleResearchOutput:
        job = jobs_repo.get_row(db, user_id, application.job_id) if application.job_id else None
        saved_jd = getattr(application, "job_description", None) or (job.description if job else None)
        request = CompanyRoleResearchInput(
            application_id=application.id,
            company_name=application.company,
            job_title=application.role,
            saved_jd=saved_jd,
        )
        if self.use_cached_profile:
            return self._run_cached_profile(db, request, force_profile_refresh=force_profile_refresh)
        official_sources = self.provider.search_company_official(request.company_name)
        community_sources = self.provider.search_interview_experience(
            request.company_name,
            request.job_title,
        )
        career_sources = self.provider.search_company_careers(request.company_name)
        campus_sources = self.provider.search_campus_recruitment(request.company_name)
        try:
            news_sources = self.provider.search_recent_news(request.company_name, request.job_title, request.saved_jd)
        except TypeError:
            news_sources = self.provider.search_recent_news(request.company_name)
        competitive_search = getattr(self.provider, "search_competitive_references", None)
        competitive_sources = (
            competitive_search(request.company_name, request.job_title, request.saved_jd)
            if callable(competitive_search)
            else []
        )
        candidate_metadata_getter = getattr(self.provider, "get_competitive_candidate_metadata", None)
        candidate_metadata = (
            candidate_metadata_getter(request.company_name)
            if callable(candidate_metadata_getter)
            else {}
        )
        candidate_alternatives_getter = getattr(self.provider, "get_competitive_candidate_alternatives", None)
        candidate_alternatives = (
            candidate_alternatives_getter(request.company_name)
            if callable(candidate_alternatives_getter)
            else {}
        )
        verification_metadata_getter = getattr(self.provider, "get_competitive_verification_metadata", None)
        verification_metadata = (
            verification_metadata_getter(request.company_name)
            if callable(verification_metadata_getter)
            else {}
        )
        provider_sources = [
            *official_sources,
            *career_sources,
            *(source for source in campus_sources if source.source_type == "official"),
            *(source for source in news_sources if source.source_type == "official"),
            *(source for source in news_sources if source.source_type == "external"),
            *competitive_sources,
            *(source for source in campus_sources if source.source_type == "campus"),
            *community_sources,
        ]
        selected_sources = self._select_fetch_sources(
            official_sources=official_sources,
            recruitment_sources=[*career_sources, *campus_sources],
            news_sources=news_sources,
            competitive_sources=competitive_sources,
            community_sources=community_sources,
        )
        fetched_sources: list[FetchedSource] = []
        evidence: list[Evidence] = []
        # Reserve one fetch attempt per selected competitive source. Successful
        # primary fetches release that capacity back to ordinary deferred sources.
        competitive_urls = {source.url.rstrip("/") for source in competitive_sources}
        reserve_count = min(2, len(competitive_urls))
        community_deferred_count = int(any(source.source_type == "community" for source in selected_sources))
        target_deferred_count = max(reserve_count, community_deferred_count)
        deferral_candidates = [
            *[source for source in selected_sources if source.source_type == "community"],
            *[source for source in selected_sources if source.source_type == "campus"],
            *reversed([source for source in selected_sources if source.url.rstrip("/") not in competitive_urls]),
        ]
        deferred_sources: list[WebSearchSource] = []
        for source in deferral_candidates if target_deferred_count else []:
            if source in deferred_sources or source.url.rstrip("/") in competitive_urls:
                continue
            deferred_sources.append(source)
            if len(deferred_sources) >= target_deferred_count:
                break
        primary_sources = [source for source in selected_sources if source not in deferred_sources]

        def fetch_and_extract(source: WebSearchSource) -> None:
            try:
                fetched = self.fetcher.fetch_source(source)
            except Exception:
                fetched = self.fetcher.failed_result(source)
            fetched_sources.append(fetched)
            evidence.extend(self.evidence_extractor.extract(
                fetched,
                company_name=request.company_name,
                job_title=request.job_title,
            ))

        for source in primary_sources:
            fetch_and_extract(source)
        competitive_fallback_diagnostics = {
            "selected_candidate_count": len(candidate_metadata),
            "fallback_source_found_count": 0,
            "fallback_fetch_success_count": 0,
            "reference_evidence_count": 0,
            "candidates": [],
        }
        fetched_by_url = {source.url.rstrip("/"): source for source in fetched_sources}
        for primary_url, metadata in list(candidate_metadata.items()):
            primary = fetched_by_url.get(primary_url.rstrip("/"))
            primary_reference_count = sum(
                item.source_id == primary.source_id
                and item.source_type == "external"
                and item.evidence_type == "competitive"
                for item in evidence
            ) if primary else 0
            alternatives = candidate_alternatives.get(primary_url.rstrip("/"), [])
            verification = verification_metadata.get(primary_url.rstrip("/"), {})
            verification_urls = set(verification.get("verification_source_urls", []))
            candidate_diagnostics = {
                "candidate_entity": metadata.entity,
                "primary_source_fetch_result": (
                    primary.error or primary.fetch_status if primary else "not_fetched"
                ),
                "alternate_source_count": len(alternatives),
                "alternate_source_attempt_count": 0,
                "alternate_source_fetch_success": 0,
                "final_reference_evidence_count": primary_reference_count,
                "verification_search_candidate": verification.get("verification_search_candidate"),
                "verification_query_category": verification.get("verification_query_category"),
                "verification_result_count": verification.get("verification_result_count", 0),
                "verification_official_source_count": verification.get("verification_official_source_count", 0),
                "verification_fetch_attempt_count": 0,
                "verification_fetch_success_count": 0,
                "verification_reference_evidence_count": 0,
            }
            competitive_fallback_diagnostics["candidates"].append(candidate_diagnostics)
            if primary and primary.fetch_status == "success" and primary_reference_count:
                competitive_fallback_diagnostics["reference_evidence_count"] += primary_reference_count
                continue
            if alternatives:
                competitive_fallback_diagnostics["fallback_source_found_count"] += 1
            for alternative in alternatives:
                if len(fetched_sources) >= 8:
                    break
                candidate_diagnostics["alternate_source_attempt_count"] += 1
                is_verification_source = alternative.url.rstrip("/") in verification_urls
                if is_verification_source:
                    candidate_diagnostics["verification_fetch_attempt_count"] += 1
                before = len(evidence)
                fetch_and_extract(alternative)
                provider_sources.append(alternative)
                fetched = fetched_sources[-1]
                reference_count = sum(
                    item.source_id == fetched.source_id
                    and item.source_type == "external"
                    and item.evidence_type == "competitive"
                    for item in evidence[before:]
                )
                if fetched.fetch_status == "success" and reference_count:
                    candidate_diagnostics["alternate_source_fetch_success"] += 1
                    candidate_diagnostics["final_reference_evidence_count"] += reference_count
                    if is_verification_source:
                        candidate_diagnostics["verification_fetch_success_count"] += 1
                        candidate_diagnostics["verification_reference_evidence_count"] += reference_count
                    competitive_fallback_diagnostics["fallback_fetch_success_count"] += 1
                    competitive_fallback_diagnostics["reference_evidence_count"] += reference_count
                    candidate_metadata.pop(primary_url, None)
                    candidate_metadata[alternative.url.rstrip("/")] = metadata
                    break
        logger.warning(
            "company_research_competitor_fetch_fallback %s",
            json.dumps(competitive_fallback_diagnostics, separators=(",", ":")),
        )
        fallback_diagnostics = self._try_recent_same_event_fallback(
            request=request,
            selected_sources=selected_sources,
            fetched_sources=fetched_sources,
            evidence=evidence,
            provider_sources=provider_sources,
            recent_candidate_pool=self._recent_candidate_pool(request.company_name),
        )
        for source in deferred_sources:
            if len(fetched_sources) >= 8:
                break
            fetch_and_extract(source)
        logger.warning(
            "company_research_recent_fallback %s",
            json.dumps(fallback_diagnostics, separators=(",", ":")),
        )
        logger.warning(
            "company_research_fetch_failures %s",
            json.dumps(self._fetch_failure_reason_counts(fetched_sources), separators=(",", ":")),
        )
        if request.saved_jd:
            saved_jd = request.saved_jd[:8_000]
            digest = sha256(saved_jd.encode()).hexdigest()[:20]
            evidence.insert(0, Evidence(
                evidence_id=f"evidence_jd_{digest}",
                source_id="source_saved_jd",
                source_type="user_provided",
                evidence_type="role",
                text=saved_jd,
            ))
        supply_diagnostics = self._build_supply_diagnostics(
            official_sources=official_sources,
            news_sources=news_sources,
            competitive_sources=competitive_sources,
            selected_sources=selected_sources,
            fetched_sources=fetched_sources,
            evidence=evidence,
        )
        dimensions = infer_competitive_dimensions(request.job_title, request.saved_jd)
        provider_diagnostics_getter = getattr(self.provider, "get_competitive_diagnostics", None)
        provider_diagnostics = (
            provider_diagnostics_getter(request.company_name)
            if callable(provider_diagnostics_getter)
            else {}
        )
        qualification_diagnostics_getter = getattr(
            self.provider, "get_competitive_qualification_diagnostics", None,
        )
        qualification_diagnostics = (
            qualification_diagnostics_getter(request.company_name)
            if callable(qualification_diagnostics_getter)
            else []
        )
        competitive_diagnostics = supply_diagnostics["competitive_context"]
        competitive_diagnostics["competitive_dimensions_count"] = provider_diagnostics.get(
            "competitive_dimensions_count", len(dimensions),
        )
        competitive_diagnostics["candidate_discovered_count"] = provider_diagnostics.get(
            "candidate_discovered_count", len(competitive_sources),
        )
        competitive_diagnostics["candidate_selected_count"] = sum(
            source.url.rstrip("/") in {item.url.rstrip("/") for item in selected_sources}
            for source in competitive_sources
        )
        competitive_diagnostics["candidate_rejected_count"] = provider_diagnostics.get(
            "candidate_rejected_count",
            max(0, len(competitive_sources) - competitive_diagnostics["candidate_selected_count"]),
        )
        candidate_bindings = self._build_competitive_candidate_bindings(
            candidate_metadata=candidate_metadata,
            fetched_sources=fetched_sources,
            evidence=evidence,
        )
        logger.warning(
            "company_research_competitor_discovery %s",
            json.dumps({
                "competitive_dimensions_count": competitive_diagnostics["competitive_dimensions_count"],
                "candidate_discovered_count": competitive_diagnostics["candidate_discovered_count"],
                "candidate_selected_count": competitive_diagnostics["candidate_selected_count"],
                "candidate_rejected_count": competitive_diagnostics["candidate_rejected_count"],
                "rejected_non_entity_count": provider_diagnostics.get("rejected_non_entity_count", 0),
                "seeded_candidate_count": provider_diagnostics.get("seeded_candidate_count", 0),
                "search_discovered_candidate_count": provider_diagnostics.get("search_discovered_candidate_count", 0),
                "merged_candidate_count": provider_diagnostics.get("merged_candidate_count", 0),
                "market_peer_search_result_count": provider_diagnostics.get("market_peer_search_result_count", 0),
                "extracted_company_candidate_count": provider_diagnostics.get("extracted_company_candidate_count", 0),
                "extracted_branded_ai_product_count": provider_diagnostics.get("extracted_branded_ai_product_count", 0),
                "primary_market_peer_count": provider_diagnostics.get("primary_market_peer_count", 0),
                "secondary_candidate_count": provider_diagnostics.get("secondary_candidate_count", 0),
                "qualification_candidates": qualification_diagnostics,
                **competitive_fallback_diagnostics,
                "candidates": [
                    {
                        "candidate_type": metadata.candidate_type,
                        "market_candidate_type": metadata.market_candidate_type,
                        "candidate_category": metadata.candidate_category,
                        "candidate_origin": metadata.candidate_origin,
                        "market_proximity_score": metadata.market_proximity_score,
                        "verification_success": metadata.verification_success,
                        "entity_type": metadata.entity_type,
                        "shared_market_dimensions": list(metadata.shared_market_dimensions),
                        "shared_ai_dimensions": list(metadata.shared_ai_dimensions),
                        "market_overlap_score": metadata.market_overlap_score,
                        "qualification_status": metadata.qualification_status,
                        "shared_dimension_count": len(metadata.shared_dimensions),
                        "official_evidence_count": metadata.official_evidence_count,
                        "third_party_evidence_count": metadata.third_party_evidence_count,
                        "final_priority": metadata.final_priority,
                    }
                    for metadata in candidate_metadata.values()
                ],
            }, separators=(",", ":")),
        )
        outcome = self.generator.generate(
            company_name=request.company_name,
            job_title=request.job_title,
            saved_jd=request.saved_jd,
            evidence=evidence,
            fetched_sources=fetched_sources,
            supply_diagnostics=supply_diagnostics,
            competitive_candidate_bindings=candidate_bindings,
        )
        return self._compose(
            request,
            provider_sources,
            fetched_sources,
            evidence,
            outcome.report,
            outcome.status,
            candidate_bindings,
            [
                {
                    "entity": metadata.entity,
                    "shared_dimensions": list(metadata.shared_dimensions),
                    "qualification_status": metadata.qualification_status,
                    "entity_type": metadata.entity_type,
                }
                for metadata in candidate_metadata.values()
                if metadata.qualification_status in {"primary_market_peer", "secondary_product_reference"}
                and metadata.entity_type in {"company", "branded_product", "branded_platform"}
            ],
        )

    @staticmethod
    def _build_competitive_candidate_bindings(
        *,
        candidate_metadata: dict[str, CompetitiveCandidateMetadata],
        fetched_sources: list[FetchedSource],
        evidence: list[Evidence],
    ) -> list[dict[str, object]]:
        fetched_by_url = {item.url.rstrip("/"): item for item in fetched_sources}
        evidence_by_source: dict[str, list[Evidence]] = {}
        for item in evidence:
            evidence_by_source.setdefault(item.source_id, []).append(item)
        target_evidence = [
            item for item in evidence
            if item.evidence_type in {"company", "role"}
            and item.source_type in {"user_provided", "official", "external", "campus"}
        ]
        bindings: list[dict[str, object]] = []
        for url, metadata in candidate_metadata.items():
            fetched = fetched_by_url.get(url.rstrip("/"))
            candidate_evidence = evidence_by_source.get(fetched.source_id, []) if fetched else []
            extracted_reference_evidence = [
                item for item in candidate_evidence
                if item.evidence_type == "competitive" and item.source_type == "external"
            ]
            matched_reference_evidence: list[Evidence] = []
            match_methods: list[str] = []
            for item in extracted_reference_evidence:
                method = CompanyRoleResearchSkill._candidate_evidence_match_method(
                    metadata.entity, fetched, item,
                )
                if method == "no_specific_match":
                    continue
                matched_reference_evidence.append(item)
                match_methods.append(method)
                # The existing grounding validator reads evidence text only.
                # Preserve source-title provenance for deterministic title/domain
                # matches without inventing any capability or product fact.
                if method in {"source_title_match", "canonical_url/domain_match"} and not (
                    CompanyRoleResearchSkill._text_mentions_candidate(item.text, metadata.entity)
                ):
                    item.text = f"{fetched.title}. {item.text}"
            reference_ids = [item.evidence_id for item in matched_reference_evidence]
            target_ids = [
                item.evidence_id for item in target_evidence
                if shared_dimensions(item.text, list(metadata.shared_dimensions))
            ]
            diagnostic = {
                "candidate_name": metadata.entity,
                "candidate_entity": metadata.entity,
                "candidate_type": metadata.candidate_type,
                "candidate_category": metadata.candidate_category,
                "shared_dimension_count": len(metadata.shared_dimensions),
                "discovered_source_count": 1,
                "official_source_count": metadata.official_evidence_count,
                "fetch_attempt_count": int(fetched is not None),
                "fetch_success_count": int(bool(fetched and fetched.fetch_status == "success")),
                "extracted_competitive_evidence_count": len(extracted_reference_evidence),
                "reference_evidence_count": len(extracted_reference_evidence),
                "evidence_entity_match_count": len(reference_ids),
                "evidence_entity_match_method": ",".join(dict.fromkeys(match_methods))
                if match_methods else "no_specific_match",
                "routed_competitive_evidence_count": len(reference_ids),
                "evidence_ids_available_to_generator_count": len(reference_ids) + len(target_ids),
                "generator_bound_reference_evidence_ids": reference_ids,
                "generator_bound_target_evidence_ids": target_ids,
            }
            if not reference_ids:
                diagnostic["action"] = (
                    "candidate_skipped_missing_specific_reference"
                    if extracted_reference_evidence
                    else "candidate_skipped_missing_reference_evidence"
                )
                logger.warning(
                    "company_research_competitor_handoff %s",
                    json.dumps(diagnostic, separators=(",", ":")),
                )
                continue
            if not target_ids:
                diagnostic["action"] = "candidate_skipped_missing_target_evidence"
                logger.warning(
                    "company_research_competitor_handoff %s",
                    json.dumps(diagnostic, separators=(",", ":")),
                )
                continue
            diagnostic["action"] = "candidate_routed_to_generator"
            logger.warning(
                "company_research_competitor_handoff %s",
                json.dumps(diagnostic, separators=(",", ":")),
            )
            bindings.append({
                "entity": metadata.entity,
                "candidate_type": metadata.candidate_type,
                "candidate_category": metadata.candidate_category,
                "shared_dimensions": list(metadata.shared_dimensions),
                "reference_side_evidence_ids": reference_ids,
                "target_side_evidence_ids": target_ids,
            })
        return bindings

    @staticmethod
    def _text_mentions_candidate(text: str, entity: str) -> bool:
        entity_key = candidate_entity_key(entity)
        if not entity_key:
            return False
        normalized_text = re.sub(r"[\s._-]+", " ", text.casefold())
        if re.search(r"[\u3400-\u9fff]", entity_key):
            return entity_key in normalized_text
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(entity_key)}(?![a-z0-9])", normalized_text))

    @staticmethod
    def _candidate_evidence_match_method(
        entity: str,
        fetched: FetchedSource | None,
        item: Evidence,
    ) -> str:
        if CompanyRoleResearchSkill._text_mentions_candidate(item.text, entity):
            return "extracted_entity_alias_match"
        if fetched and CompanyRoleResearchSkill._text_mentions_candidate(fetched.title, entity):
            return "source_title_match"
        if fetched:
            host = (urlparse(fetched.url).hostname or "").casefold()
            compact_entity = re.sub(r"[^a-z0-9]", "", candidate_entity_key(entity))
            host_labels = {re.sub(r"[^a-z0-9]", "", label) for label in host.split(".")}
            if len(compact_entity) >= 3 and compact_entity in host_labels:
                return "canonical_url/domain_match"
        return "no_specific_match"

    @staticmethod
    def _build_supply_diagnostics(
        *,
        official_sources: list[WebSearchSource],
        news_sources: list[WebSearchSource],
        competitive_sources: list[WebSearchSource],
        selected_sources: list[WebSearchSource],
        fetched_sources: list[FetchedSource],
        evidence: list[Evidence],
    ) -> dict[str, dict[str, int]]:
        def urls(items: list[Any]) -> set[str]:
            return {str(item.url).rstrip("/") for item in items}

        official_urls = urls(official_sources)
        news_urls = urls(news_sources)
        selected_by_url = {str(item.url).rstrip("/") for item in selected_sources}
        fetched_by_url = {str(item.url).rstrip("/"): item for item in fetched_sources}

        def fetch_counts(candidate_urls: set[str]) -> tuple[int, int]:
            attempted = candidate_urls & selected_by_url
            succeeded = sum(
                fetched_by_url[url].fetch_status == "success"
                for url in attempted
                if url in fetched_by_url
            )
            return len(attempted), succeeded

        company_urls = official_urls | news_urls
        company_attempts, company_successes = fetch_counts(company_urls)
        recent_attempts, recent_successes = fetch_counts(news_urls)
        competitive_urls = urls(competitive_sources)
        competitive_attempts, competitive_successes = fetch_counts(competitive_urls)
        company_evidence = [item for item in evidence if item.evidence_type == "company"]
        recent_evidence = [item for item in evidence if item.evidence_type == "recent_signal"]
        competitive_evidence = [item for item in evidence if item.evidence_type == "competitive"]

        def count_company_markers(markers: tuple[str, ...]) -> int:
            return sum(any(marker in item.text.casefold() for marker in markers) for item in company_evidence)

        outside_90_days = sum(
            fetched.fetch_status == "success"
            and fetched.url.rstrip("/") in news_urls
            and not EvidenceExtractor._is_recent_publication(fetched.published_at)
            for fetched in fetched_sources
        )
        return {
            "company_map": {
                "discovered_candidate_count": len(company_urls),
                "fetch_attempt_count": company_attempts,
                "fetch_success_count": company_successes,
                "extracted_evidence_count": len(company_evidence),
                "routed_evidence_count": 0,
                "valid_item_count": 0,
                "company_positioning_evidence_count": count_company_markers(("公司", "企业", "company", "集团")),
                "core_business_evidence_count": count_company_markers(("业务", "产品", "服务", "business", "product", "service")),
                "customers_evidence_count": count_company_markers(("用户", "客户", "消费者", "开发者", "合作伙伴", "customer", "consumer", "user")),
                "current_focus_evidence_count": count_company_markers(("重点", "战略", "投入", "布局", "推进", "focus", "strategy", "invest")),
            },
            "recent_signals": {
                "discovered_candidate_count": len(news_urls),
                "candidates_with_valid_date": sum(
                    EvidenceExtractor._is_recent_publication(source.published_at)
                    for source in news_sources
                ),
                "fetch_attempt_count": recent_attempts,
                "fetch_success_count": recent_successes,
                "extracted_evidence_count": len(recent_evidence),
                "routed_evidence_count": 0,
                "valid_item_count": 0,
                "dropped_missing_company_anchor": 0,
                "dropped_outside_90_days": outside_90_days,
                "dropped_low_role_relevance": 0,
                "dropped_duplicate_event": 0,
            },
            "competitive_context": {
                "discovered_candidate_count": len(competitive_urls),
                "fetch_attempt_count": competitive_attempts,
                "fetch_success_count": competitive_successes,
                "extracted_evidence_count": len(competitive_evidence),
                "routed_evidence_count": 0,
                "valid_item_count": 0,
                "competitive_dimensions_count": 0,
                "candidate_discovered_count": len(competitive_urls),
                "candidate_selected_count": competitive_attempts,
                "candidate_rejected_count": max(0, len(competitive_urls) - competitive_attempts),
                "candidate_reference_count": 0,
                "dropped_missing_specific_entity": 0,
                "dropped_missing_shared_dimension": 0,
                "dropped_unsupported_reference_point": 0,
            },
        }

    @staticmethod
    def _fetch_failure_reason_counts(fetched_sources: list[FetchedSource]) -> dict[str, int]:
        counts = {
            "timeout": 0,
            "non_html": 0,
            "blocked_or_captcha": 0,
            "http_error": 0,
            "redirect_rejected": 0,
            "content_too_small": 0,
            "dynamic_page_unreadable": 0,
            "security_rejection": 0,
        }
        for source in fetched_sources:
            error = source.error or ""
            if source.fetch_status == "success":
                continue
            if error == "timeout":
                key = "timeout"
            elif error == "unsupported_content_type":
                key = "non_html"
            elif error in {"http_401", "http_403", "http_429"}:
                key = "blocked_or_captcha"
            elif error.startswith("http_") or error in {"fetch_error", "response_too_large"}:
                key = "http_error"
            elif error == "redirect_rejected" or error in {"redirect_without_location", "too_many_redirects"}:
                key = "redirect_rejected"
            elif error == "empty_content":
                key = "content_too_small"
            elif error == "insufficient_content":
                key = "dynamic_page_unreadable"
            else:
                key = "security_rejection"
            counts[key] += 1
        return counts

    def _recent_candidate_pool(self, company_name: str) -> list[WebSearchSource]:
        getter = getattr(self.provider, "get_recent_candidate_pool", None)
        if not callable(getter):
            return []
        return list(getter(company_name))

    def _try_recent_same_event_fallback(
        self,
        *,
        request: CompanyRoleResearchInput,
        selected_sources: list[WebSearchSource],
        fetched_sources: list[FetchedSource],
        evidence: list[Evidence],
        provider_sources: list[WebSearchSource],
        recent_candidate_pool: list[WebSearchSource],
    ) -> dict[str, int]:
        diagnostics = {
            "dynamic_candidate_count": 0,
            "same_event_alternative_found": 0,
            "same_event_alternative_fetch_success": 0,
            "same_event_alternative_fetch_failed": 0,
            "no_same_event_alternative": 0,
        }
        if len(fetched_sources) >= 8 or not recent_candidate_pool:
            return diagnostics
        news_by_url = {source.url.rstrip("/"): source for source in recent_candidate_pool}
        selected_urls = {source.url.rstrip("/") for source in selected_sources}
        attempted_urls = {source.url.rstrip("/") for source in fetched_sources}
        dynamic_sources = [
            news_by_url[fetched.url.rstrip("/")]
            for fetched in fetched_sources
            if fetched.error == "insufficient_content" and fetched.url.rstrip("/") in news_by_url
        ]
        diagnostics["dynamic_candidate_count"] = len(dynamic_sources)
        for dynamic_source in dynamic_sources:
            if len(fetched_sources) >= 8:
                break
            alternatives = [
                candidate for candidate in recent_candidate_pool
                if candidate.url.rstrip("/") not in attempted_urls
                and candidate.url.rstrip("/") not in selected_urls
                and EvidenceExtractor._is_recent_publication(candidate.published_at)
                and self._same_event(dynamic_source, candidate)
            ]
            if not alternatives:
                diagnostics["no_same_event_alternative"] += 1
                continue
            diagnostics["same_event_alternative_found"] += 1
            alternative = alternatives[0]
            attempted_urls.add(alternative.url.rstrip("/"))
            fetched = self.fetcher.fetch_source(alternative)
            fetched_sources.append(fetched)
            selected_sources.append(alternative)
            if alternative not in provider_sources:
                provider_sources.append(alternative)
            extracted = self.evidence_extractor.extract(
                fetched,
                company_name=request.company_name,
                job_title=request.job_title,
            )
            has_recent_company_evidence = any(
                item.evidence_type == "recent_signal"
                and request.company_name.casefold() in item.text.casefold()
                for item in extracted
            )
            if fetched.fetch_status == "success" and has_recent_company_evidence:
                evidence.extend(extracted)
                diagnostics["same_event_alternative_fetch_success"] += 1
                break
            diagnostics["same_event_alternative_fetch_failed"] += 1
        return diagnostics

    @classmethod
    def _same_event(cls, first: WebSearchSource, second: WebSearchSource) -> bool:
        first_tokens = cls._event_identity_tokens(first.title)
        second_tokens = cls._event_identity_tokens(second.title)
        shared = first_tokens & second_tokens
        if not shared:
            return False
        distinctive_shared = {
            token for token in shared
            if any(character.isdigit() for character in token)
            or "-" in token
            or len(token) >= 5
        }
        union = first_tokens | second_tokens
        overlap = len(shared) / len(union) if union else 0
        first_date = EvidenceExtractor._normalize_publication_date(first.published_at)
        second_date = EvidenceExtractor._normalize_publication_date(second.published_at)
        dates_close = bool(first_date and second_date and abs((first_date - second_date).days) <= 7)
        return bool(distinctive_shared and (dates_close or overlap >= 0.45))

    @staticmethod
    def _event_identity_tokens(title: str) -> set[str]:
        normalized = title.casefold()
        generic = {
            "xiaomi", "小米", "发布", "推出", "更新", "最新", "产品", "平台", "模型",
            "agent", "ai", "llm", "news", "official", "公司", "集团",
        }
        tokens = set(re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", normalized))
        tokens.update(
            chunk[index:index + 2]
            for chunk in re.findall(r"[\u3400-\u9fff]+", normalized)
            for index in range(max(len(chunk) - 1, 1))
        )
        return {token for token in tokens if token not in generic and len(token) >= 2}

    def _compose(
        self,
        request: CompanyRoleResearchInput,
        provider_sources: list[WebSearchSource],
        fetched_sources: list[FetchedSource],
        evidence: list[Evidence],
        report: GroundedResearchGeneration,
        generation_status: GenerationStatus,
        candidate_bindings: list[dict[str, object]] | None = None,
        competitive_reference_candidates: list[dict[str, object]] | None = None,
        watch_topics: list[str] | None = None,
        profile_generated_at: datetime | None = None,
        profile_refreshed_at: datetime | None = None,
        profile_is_stale: bool = False,
        profile_cache_hit: bool = False,
        company_knowledge: CompanyKnowledge | None = None,
        company_knowledge_source_ids: dict[str, list[str]] | None = None,
        company_knowledge_sources: list[CompanyKnowledgeSource] | None = None,
        include_interview_answer_fallback: bool = True,
        build_interview_references: bool = True,
    ) -> CompanyRoleResearchOutput:
        sources: list[SourceMetadata] = []

        def add_source(source: SourceMetadata) -> int:
            if source not in sources:
                sources.append(source)
            return sources.index(source)

        add_source(SourceMetadata(source_type="user_provided", title="Saved application"))

        if request.saved_jd:
            add_source(SourceMetadata(source_type="user_provided", title="Saved job description"))

        if any(item.source_type == "ai_inference" for item in evidence):
            add_source(SourceMetadata(source_type="ai_inference", title="AI-generated company profile"))

        for source in provider_sources:
            add_source(SourceMetadata(**source.model_dump()))

        interview_references = self._build_interview_references(
            request=request,
            report=report,
            candidate_bindings=candidate_bindings or [],
            competitive_reference_candidates=competitive_reference_candidates or [],
            watch_topics=watch_topics or [],
            include_interview_answer_fallback=include_interview_answer_fallback,
        ) if build_interview_references else InterviewReferenceFallbacks()
        if generation_status == "unavailable" and any((
            interview_references.recent_signals_status == "interview_reference",
            interview_references.competitive_context_status == "interview_reference",
            interview_references.why_company_role_status == "interview_reference",
        )):
            generation_status = "partial"
        return CompanyRoleResearchOutput(
            application_id=request.application_id,
            company_name=request.company_name,
            job_title=request.job_title,
            company_map=report.company_map,
            role_decoder=report.role_decoder,
            recent_signals=report.recent_signals,
            competitive_context=report.competitive_context,
            likely_interview_focus=report.likely_interview_focus,
            why_company_why_role_60s=report.why_company_why_role_60s,
            reverse_questions=report.reverse_questions,
            sources=sources,
            fetched_sources=fetched_sources,
            evidence=evidence,
            interview_references=interview_references,
            generation_status=generation_status,
            company_profile_generated_at=profile_generated_at.isoformat() if profile_generated_at else None,
            company_profile_refreshed_at=profile_refreshed_at.isoformat() if profile_refreshed_at else None,
            company_profile_is_stale=profile_is_stale,
            company_profile_cache_hit=profile_cache_hit,
            company_knowledge=company_knowledge or CompanyKnowledge(),
            company_knowledge_source_ids=company_knowledge_source_ids or {},
            company_knowledge_sources=company_knowledge_sources or [],
        )

    @staticmethod
    def _build_interview_references(
        *,
        request: CompanyRoleResearchInput,
        report: GroundedResearchGeneration,
        candidate_bindings: list[dict[str, object]],
        competitive_reference_candidates: list[dict[str, object]] | None = None,
        watch_topics: list[str] | None = None,
        include_interview_answer_fallback: bool = True,
    ) -> InterviewReferenceFallbacks:
        """Build low-risk preparation guidance without another external or AI call."""
        result = InterviewReferenceFallbacks()
        fallback_reasons: dict[str, str] = {}

        if report.recent_signals.status == "unavailable" and request.job_title:
            context = f"{request.job_title} {request.saved_jd or ''}".casefold()
            topics: list[tuple[str, str]] = []
            for topic in (watch_topics or [])[:3]:
                topics.append((
                    topic,
                    "这是公司资料中值得面试前关注的方向；它不是实时新闻，建议结合岗位职责准备产品与业务理解。",
                ))
            if not topics and re.search(r"ai|agent|智能体|大模型|llm|人工智能", context, re.I):
                topics.append((
                    f"{request.company_name} 的 AI / Agent 产品进展",
                    "当前岗位涉及 AI 产品能力，面试前可以继续留意相关产品、平台能力和实际应用场景。",
                ))
            if re.search(r"跨设备|多终端|终端|手机|smartphone|device|ecosystem", context, re.I):
                topics.append((
                    f"{request.company_name} 的多终端智能体验",
                    "岗位场景涉及终端或跨设备协同，可以重点关注 AI 助手入口、任务流转和设备间体验。",
                ))
            if not topics:
                topics.append((
                    f"{request.company_name} 与{request.job_title}相关的产品方向",
                    "当前没有满足时间与证据要求的近期动态，面试前可继续关注与岗位职责直接相关的产品变化。",
                ))
            result.recent_signals_status = "interview_reference"
            result.recent_signals = [
                {
                    "watch_topic": topic,
                    "why_relevant": reason,
                    "what_to_learn": ["目标用户与核心场景", "产品能力与岗位职责的连接点"],
                }
                for topic, reason in topics[:3]
            ]
            fallback_reasons["recent_signals"] = "insufficient_recent_grounding"

        if report.competitive_context.status == "unavailable":
            items = []
            candidate_pool = [*candidate_bindings, *(competitive_reference_candidates or [])]
            seen_entities: set[str] = set()
            for binding in candidate_pool:
                entity = str(binding.get("entity") or "").strip()
                dimensions = [str(value) for value in binding.get("shared_dimensions", []) if value]
                entity_key = candidate_entity_key(entity)
                if not entity or not dimensions or not entity_key or entity_key in seen_entities:
                    continue
                seen_entities.add(entity_key)
                dimension = "、".join(dimensions[:3])
                items.append({
                    "entity_name": entity,
                    "reference_type": binding.get("reference_type", "comparable_product"),
                    "shared_dimension": dimension,
                    "why_relevant": binding.get("why_relevant") or f"它与当前岗位共享{dimension}等产品场景，适合作为面试前的同类产品参考。",
                    "interview_angle": binding.get("interview_angle") or "可以比较用户入口、任务执行方式、工作流、工具能力和实际场景落地，不把它直接认定为官方竞品。",
                })
            if items:
                result.competitive_context_status = "interview_reference"
                result.competitive_context = items[:3]
                fallback_reasons["competitive_context"] = "insufficient_competitor_grounding"

        if (
            include_interview_answer_fallback
            and
            report.why_company_why_role_60s.status == "unavailable"
            and report.company_map.status == "available"
            and (report.role_decoder.status == "available" or bool(request.saved_jd and request.job_title))
        ):
            company_reason = report.company_map.items[0].text
            role_reason = (
                report.role_decoder.items[0].text
                if report.role_decoder.status == "available"
                else f"{request.job_title}会围绕岗位职责、产品场景和实际落地展开"
            )
            motivation = "我希望进一步理解 AI 或产品能力如何变成用户真正能用的产品。"
            sample = (
                f"我比较关注{request.company_name}，因为{company_reason.rstrip('。')}。"
                f"这个岗位吸引我的地方是，{role_reason.rstrip('。')}。"
                f"对我来说，{motivation}这也是我希望继续深入的方向。"
            )
            for repeated, replacement in (("这个这个", "这个"), ("岗位岗位", "岗位"), ("公司公司", "公司")):
                sample = sample.replace(repeated, replacement)
            result.why_company_role_status = "interview_reference"
            result.why_company_role = {
                "company_reason": company_reason,
                "role_reason": role_reason,
                "personal_motivation_prompt": motivation,
                "sample_answer": sample,
            }
            fallback_reasons["why_company_why_role_60s"] = "strict_why_validation_failed"

        for section, reason in fallback_reasons.items():
            logger.warning(
                "company_research_interview_reference %s",
                json.dumps({
                    "section": section,
                    "strict_status": "unavailable",
                    "fallback_status": "interview_reference",
                    "fallback_reason": reason,
                }, separators=(",", ":")),
            )
        return InterviewReferenceFallbacks.model_validate(result.model_dump(warnings=False))

    @staticmethod
    def _select_fetch_sources(
        *,
        official_sources: list[WebSearchSource],
        recruitment_sources: list[WebSearchSource],
        news_sources: list[WebSearchSource],
        competitive_sources: list[WebSearchSource],
        community_sources: list[WebSearchSource],
    ) -> list[WebSearchSource]:
        selected: list[WebSearchSource] = []
        seen_urls: set[str] = set()

        def add_group(sources: list[WebSearchSource], limit: int) -> None:
            added = 0
            for source in sources:
                normalized_url = source.url.rstrip("/")
                if normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                selected.append(source)
                added += 1
                if added >= limit or len(selected) >= 8:
                    return

        def add_company_group(sources: list[WebSearchSource], limit: int) -> None:
            ranked = sorted(sources, key=CompanyRoleResearchSkill._company_source_rank)
            selected_categories: set[str] = set()
            for prefer_new_category in (True, False):
                for source in ranked:
                    if len(selected) >= 8:
                        return
                    normalized_url = source.url.rstrip("/")
                    category = CompanyRoleResearchSkill._company_source_category(source)
                    if normalized_url in seen_urls:
                        continue
                    if prefer_new_category and category in selected_categories:
                        continue
                    seen_urls.add(normalized_url)
                    selected.append(source)
                    selected_categories.add(category)
                    if len(selected_categories) >= limit or sum(
                        item.url.rstrip("/") in seen_urls for item in sources
                    ) >= limit:
                        return

        add_company_group(official_sources, 2)
        add_group(recruitment_sources, 1)
        add_group(competitive_sources, 2)
        add_group(news_sources, 2)
        add_group(community_sources, 1)
        return selected[:8]

    @staticmethod
    def _company_source_category(source: WebSearchSource) -> str:
        text = f"{source.title} {source.url} {source.snippet}".casefold()
        categories = (
            ("positioning", ("about", "company profile", "corporate profile", "公司介绍", "关于我们", "集团介绍", "公司概况")),
            ("core_business", ("product", "business", "ecosystem", "产品", "业务", "生态")),
            ("customers", ("customer", "consumer", "user", "client", "客户", "用户", "消费者", "开发者", "合作伙伴")),
            ("current_focus", ("strategy", "focus", "invest", "战略", "重点", "投入", "布局")),
            ("investor", ("investor", "annual report", "ir.", "投资者", "年报")),
            ("careers", ("career", "jobs", "招聘", "加入我们")),
            ("platform", ("platform", "developer", "平台", "开发者")),
        )
        return next((category for category, markers in categories if any(marker in text for marker in markers)), "other")

    @staticmethod
    def _company_source_rank(source: WebSearchSource) -> tuple[int, str]:
        priorities = {
            "positioning": 0,
            "core_business": 1,
            "investor": 2,
            "customers": 3,
            "current_focus": 4,
            "careers": 5,
            "platform": 6,
            "other": 7,
        }
        return priorities[CompanyRoleResearchSkill._company_source_category(source)], source.url

    @staticmethod
    def _company_profile_source_category(source: WebSearchSource) -> str:
        identity = f"{source.title} {source.url}".casefold()
        context = f"{identity} {source.snippet}".casefold()
        categories = (
            ("overview", ("about", "company profile", "corporate profile", "company overview", "关于", "公司简介", "集团介绍", "公司概况")),
            ("investor", ("investor", "annual report", "financial report", "ir.", "/ir/", "投资者", "年报", "财报")),
            ("platform_ecosystem", ("platform", "ecosystem", "operating system", "developer", "hyperos", "aiot", "iot", "平台", "生态", "操作系统", "开发者")),
            ("strategic_product", ("electric vehicle", "automotive", "smartphone", "product", "汽车", "智能手机", "产品", "智能家居")),
            ("careers", ("career", "jobs", "招聘", "加入我们")),
        )
        direct = next((category for category, markers in categories if any(marker in identity for marker in markers)), None)
        if direct:
            return direct
        return next((category for category, markers in categories if any(marker in context for marker in markers)), "other")

    @staticmethod
    def _same_official_organization_sources(sources: list[WebSearchSource]) -> list[WebSearchSource]:
        """Keep the primary official organization's HTML domain and sibling subdomains."""
        if not sources:
            return []

        def organization_domain(url: str) -> str:
            host = (urlparse(url).hostname or "").casefold().strip(".")
            labels = host.split(".")
            if len(labels) <= 2:
                return host
            if ".".join(labels[-2:]) in {"com.cn", "net.cn", "org.cn", "gov.cn"}:
                return ".".join(labels[-3:])
            return ".".join(labels[-2:])

        primary_domain = organization_domain(sources[0].url)
        return [
            source for source in sources
            if organization_domain(source.url) == primary_domain
            and not urlparse(source.url).path.casefold().endswith(".pdf")
        ]

    @classmethod
    def _profile_research_candidates(cls, sources: list[WebSearchSource]) -> list[WebSearchSource]:
        """Keep one official organization plus already-trusted external fallbacks."""
        official = [source for source in sources if source.source_type == "official"]
        external = [source for source in sources if source.source_type == "external"]
        filtered_official = cls._same_official_organization_sources(official)
        return [*filtered_official, *external]

    @classmethod
    def _select_profile_round_sources(
        cls,
        sources: list[WebSearchSource],
        *,
        missing_dimensions: list[str],
        seen_urls: set[str],
        limit: int,
    ) -> list[WebSearchSource]:
        """Choose pages that complement accumulated evidence instead of repeating About pages."""
        dimension_categories = {
            "company_overview": ("overview", "investor"),
            "core_business": ("investor", "overview", "strategic_product"),
            "brands_products": ("strategic_product", "platform_ecosystem", "overview"),
            "platforms_ecosystem": ("platform_ecosystem", "strategic_product"),
            "strategic_business": ("strategic_product", "investor"),
            "customer_market": ("overview", "investor"),
            "role_relevant_context": ("platform_ecosystem", "strategic_product"),
            "comparable_context": ("other",),
        }
        category_order: list[str] = []
        for dimension in missing_dimensions:
            for category in dimension_categories.get(dimension, ("other",)):
                if category not in category_order:
                    category_order.append(category)
        for category in ("overview", "investor", "platform_ecosystem", "strategic_product", "careers", "other"):
            if category not in category_order:
                category_order.append(category)

        available = [source for source in sources if source.url.rstrip("/") not in seen_urls]
        available.sort(key=lambda source: (
            0 if source.source_type == "official" else 1,
            category_order.index(cls._company_profile_source_category(source)),
            source.url,
        ))
        selected: list[WebSearchSource] = []
        selected_categories: set[str] = set()
        for prefer_new_category in (True, False):
            for source in available:
                if source in selected:
                    continue
                category = cls._company_profile_source_category(source)
                if prefer_new_category and category in selected_categories:
                    continue
                selected.append(source)
                selected_categories.add(category)
                if len(selected) >= limit:
                    return selected
        return selected

    @classmethod
    def _select_company_profile_sources(
        cls,
        sources: list[WebSearchSource],
        *,
        limit: int = 4,
    ) -> list[WebSearchSource]:
        """Select complementary official pages from one search result pool."""
        category_order = ("overview", "investor", "platform_ecosystem", "strategic_product", "careers", "other")
        selected: list[WebSearchSource] = []
        seen_urls: set[str] = set()
        for category in category_order:
            candidate = next((
                source for source in sources
                if cls._company_profile_source_category(source) == category
                and source.url.rstrip("/") not in seen_urls
            ), None)
            if candidate:
                selected.append(candidate)
                seen_urls.add(candidate.url.rstrip("/"))
            if len(selected) >= limit:
                return selected
        for source in sources:
            normalized_url = source.url.rstrip("/")
            if normalized_url in seen_urls:
                continue
            selected.append(source)
            seen_urls.add(normalized_url)
            if len(selected) >= limit:
                break
        return selected

company_role_research_skill = CompanyRoleResearchSkill(
    create_company_research_provider(settings.tavily_api_key),
    use_cached_profile=True,
)
