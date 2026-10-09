from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import applications as applications_api
from app.skills.company_role_research.schemas import (
    CompanyMapSection,
    CompanyRoleResearchInput,
    Evidence,
    FetchedSource,
    RoleDecoderSection,
    SourceMetadata,
    RoleRelevantProductItem,
    WebSearchSource,
)
from app.skills.company_role_research.generator import GenerationOutcome, unavailable_report
from app.skills.company_role_research.skill import CompanyRoleResearchSkill
from app.skills.company_role_research import skill as skill_module
from app.skills.company_role_research.competitive_discovery import CompetitiveCandidateMetadata
from app.skills.company_role_research.profile import CompanyProfileDraft
from app.skills.company_role_research.profile import normalize_profile_draft
from app.skills.company_role_research.profile_research import plan_profile_search


class StaticProvider:
    def __init__(self, *, official=None, careers=None, news=None, competitive=None, campus=None, community=None):
        self.official = official or []
        self.careers = careers or []
        self.news = news or []
        self.competitive = competitive or []
        self.campus = campus or []
        self.community = community or []
        self.calls = []

    def search_company_official(self, company_name):
        self.calls.append(("official", company_name))
        return self.official

    def search_company_careers(self, company_name):
        self.calls.append(("careers", company_name))
        return self.careers

    def search_recent_news(self, company_name):
        self.calls.append(("news", company_name))
        return self.news

    def search_campus_recruitment(self, company_name):
        self.calls.append(("campus", company_name))
        return self.campus

    def search_competitive_references(self, company_name, job_title=None, saved_jd=None):
        self.calls.append(("competitive", company_name, job_title))
        return self.competitive

    def search_interview_experience(self, company_name, job_title=None):
        self.calls.append(("community", company_name, job_title))
        return self.community


class UnavailableFetcher:
    def fetch_source(self, source):
        return self.failed_result(source, "test_fetch_disabled")

    def failed_result(self, source, error="fetch_error"):
        return FetchedSource(
            source_id="source_test",
            title=source.title,
            url=source.url,
            source_type=source.source_type,
            published_at=source.published_at,
            fetch_status="unavailable",
            error=error,
        )


class SuccessfulFetcher:
    def __init__(self):
        self.calls = 0

    def fetch_source(self, source):
        self.calls += 1
        return FetchedSource(
            source_id=f"source_{self.calls}", title=source.title, url=source.url,
            source_type=source.source_type, published_at=source.published_at,
            content_type="text/html", fetch_status="success",
            extracted_text="Example Co company business products serve consumers and enterprise customers.",
        )


class QueryProvider:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.queries = []

    def search_company_profile(self, company_name, query):
        self.queries.append(query)
        index = len(self.queries) - 1
        return self.rounds[index] if index < len(self.rounds) else []


class ContentFetcher:
    def __init__(self, content_by_url):
        self.content_by_url = content_by_url
        self.calls = []

    def fetch_source(self, source):
        self.calls.append(source.url)
        content = self.content_by_url.get(source.url, "")
        return FetchedSource(
            source_id=f"source_{len(self.calls)}", title=source.title, url=source.url,
            source_type=source.source_type, content_type="text/html",
            fetch_status="success" if content else "unavailable",
            extracted_text=content, error=None if content else "content_too_small",
        )


class UnavailableGenerator:
    def generate(self, **kwargs):
        return GenerationOutcome(unavailable_report(), "unavailable")


class StaticProfileGenerator:
    def __init__(self):
        self.calls = 0

    def generate(self, company_name):
        self.calls += 1
        return CompanyProfileDraft(
            positioning=f"{company_name} is a consumer technology company.",
            business_lines=["Devices", "Software"],
            customer_groups=["Consumers"],
            strategic_focus=["AI product experiences"],
        )

    def persistence_values(self, company_name, draft):
        now = datetime.now(timezone.utc)
        return {"company_name": company_name, **draft.model_dump(), "model_name": "test", "generation_version": "test", "generated_at": now, "refreshed_at": now}


class FakeDb:
    def commit(self): pass
    def refresh(self, row): pass


def application(*, job_id=None, job_description=None):
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        job_id=job_id,
        job_description=job_description,
        company="Example Co",
        role="Product Manager",
    )


def test_valid_application_loads_company_role_and_saved_jd(monkeypatch):
    app = application(job_id=uuid4())
    provider = StaticProvider()
    monkeypatch.setattr(skill_module.jobs_repo, "get_row", lambda db, user_id, job_id: SimpleNamespace(description="Saved JD text"))

    result = CompanyRoleResearchSkill(provider, generator=UnavailableGenerator()).run(object(), app.user_id, app)

    assert result.company_name == "Example Co"
    assert result.job_title == "Product Manager"
    assert result.role_decoder.status == "unavailable"
    assert result.evidence[0].source_type == "user_provided"
    assert result.evidence[0].evidence_type == "role"
    assert result.evidence[0].text == "Saved JD text"
    assert provider.calls == [
        ("official", "Example Co"),
        ("community", "Example Co", "Product Manager"),
        ("careers", "Example Co"),
        ("campus", "Example Co"),
        ("news", "Example Co"),
        ("competitive", "Example Co", "Product Manager"),
    ]
    assert result.sources[1].source_type == "user_provided"


def test_cached_profile_is_shared_and_manual_refresh_is_explicit(monkeypatch):
    stored = {}
    profile_generator = StaticProfileGenerator()
    provider = StaticProvider()

    monkeypatch.setattr(skill_module.company_profiles_repo, "get", lambda db, key: stored.get(key))

    def upsert(db, key, values):
        row = SimpleNamespace(**values)
        stored[key] = row
        return row

    monkeypatch.setattr(skill_module.company_profiles_repo, "upsert", upsert)
    skill = CompanyRoleResearchSkill(
        provider,
        generator=UnavailableGenerator(),
        profile_generator=profile_generator,
        use_cached_profile=True,
    )
    first = skill.run(FakeDb(), uuid4(), application(job_description="JD one"))
    second_app = application(job_description="JD two")
    second_app.company = "Example Co., Ltd."
    second = skill.run(FakeDb(), uuid4(), second_app)

    assert profile_generator.calls == 1
    assert first.company_profile_cache_hit is False
    assert second.company_profile_cache_hit is True
    assert provider.calls == [("official", "Example Co")]
    assert any(item.text == "JD two" for item in second.evidence)
    assert second.likely_interview_focus.status == "unavailable"
    assert second.why_company_why_role_60s.status == "unavailable"
    assert second.reverse_questions.status == "unavailable"
    assert second.interview_references.why_company_role is None

    skill.run(FakeDb(), uuid4(), second_app, force_profile_refresh=True)
    assert profile_generator.calls == 2
    assert provider.calls == [("official", "Example Co"), ("official", "Example Co., Ltd.")]


def test_profile_refresh_retrieves_lightweight_sources_and_cache_hit_does_not(monkeypatch):
    stored = {}
    sources = [WebSearchSource(title=f"Official {index}", url=f"https://example.com/{index}", source_type="official") for index in range(6)]
    provider = StaticProvider(official=sources)
    fetcher = SuccessfulFetcher()
    profile_generator = StaticProfileGenerator()
    monkeypatch.setattr(skill_module.company_profiles_repo, "get", lambda db, key: stored.get(key))

    def upsert(db, key, values):
        stored[key] = SimpleNamespace(**values)
        return stored[key]

    monkeypatch.setattr(skill_module.company_profiles_repo, "upsert", upsert)
    skill = CompanyRoleResearchSkill(provider, fetcher=fetcher, generator=UnavailableGenerator(), profile_generator=profile_generator, use_cached_profile=True)
    first = skill.run(FakeDb(), uuid4(), application(job_description="AI Agent JD"))
    second = skill.run(FakeDb(), uuid4(), application(job_description="AI Agent JD"))

    assert provider.calls == [("official", "Example Co")]
    assert fetcher.calls == 3
    assert first.company_knowledge_sources
    assert first.company_knowledge_source_ids["company_positioning"]
    assert len(first.company_knowledge_source_ids["core_business"]) == 3
    assert second.company_profile_cache_hit is True
    assert fetcher.calls == 3


def test_missing_platform_context_triggers_targeted_second_search_and_stops_early():
    round_one = [
        WebSearchSource(title="Example About", url="https://example.com/about", source_type="official"),
        WebSearchSource(title="Example investor business", url="https://ir.example.com/business", source_type="official"),
        WebSearchSource(title="Example products", url="https://example.com/products", source_type="official"),
    ]
    round_two = [
        WebSearchSource(title="ExampleOS platform", url="https://example.com/platform", source_type="official"),
        WebSearchSource(title="Example ecosystem", url="https://example.com/ecosystem", source_type="official"),
    ]
    provider = QueryProvider([round_one, round_two])
    fetcher = ContentFetcher({
        "https://example.com/about": "Example Co company overview serves consumer markets.",
        "https://ir.example.com/business": "Example Co core business includes devices and digital services products.",
        "https://example.com/products": "Example Co products include Example Phone and Example Home devices.",
        "https://example.com/platform": "Example Co AI Agent platform and operating system support cross-device workflows.",
        "https://example.com/ecosystem": "Example Co AI assistant ecosystem connects IoT devices and knowledge services.",
    })
    request = CompanyRoleResearchInput(
        application_id=uuid4(), company_name="Example Co", job_title="AI Agent Product Manager",
        saved_jd="Build AI Agent workflow, assistant, and cross-device experiences.",
    )

    result = CompanyRoleResearchSkill(provider, fetcher=fetcher)._research_company_profile(request)
    diagnostics = result[-1]

    assert len(provider.queries) == 2
    assert "核心业务" in provider.queries[0]
    assert "平台 生态 操作系统" in provider.queries[1]
    assert "agent" in provider.queries[1].casefold()
    assert diagnostics["stop_reason"] == "coverage_sufficient"
    assert diagnostics["coverage"]["platforms_ecosystem"] == "sufficient"
    assert diagnostics["coverage"]["role_relevant_context"] == "sufficient"
    assert len(fetcher.calls) == 5


def test_overview_coverage_changes_next_query_to_business_platform_gap():
    coverage = {
        "company_overview": "sufficient", "core_business": "missing",
        "brands_products": "missing", "platforms_ecosystem": "missing",
        "strategic_business": "missing", "customer_market": "missing",
        "role_relevant_context": "missing", "comparable_context": "missing",
    }

    plan = plan_profile_search(
        "Example Co", job_title="AI Agent Product Manager",
        saved_jd="Build cross-device Agent workflows.", coverage=coverage,
    )

    assert plan.reason == "complete_business_products_and_role_context"
    assert "核心业务 产品 平台 生态 操作系统" in plan.search_query
    assert "agent" in plan.search_query.casefold()
    assert "关于我们" not in plan.search_query


def test_no_new_evidence_stops_bounded_profile_research():
    provider = QueryProvider([[
        WebSearchSource(title="Empty official", url="https://example.com/empty", source_type="official"),
    ]])
    request = CompanyRoleResearchInput(application_id=uuid4(), company_name="Example Co")

    result = CompanyRoleResearchSkill(
        provider, fetcher=ContentFetcher({"https://example.com/empty": "Navigation and legal notice only."}),
    )._research_company_profile(request)

    assert result[-1]["search_count"] == 1
    assert result[-1]["stop_reason"] == "no_new_evidence"


def test_profile_research_never_exceeds_search_or_fetch_budgets():
    rounds = []
    content = {}
    for round_index in range(3):
        sources = []
        for item_index in range(2):
            url = f"https://example.com/{round_index}/{item_index}"
            sources.append(WebSearchSource(title="Official page", url=url, source_type="official"))
            content[url] = "Example Co business product information."
        rounds.append(sources)
    provider = QueryProvider(rounds)
    fetcher = ContentFetcher(content)
    request = CompanyRoleResearchInput(
        application_id=uuid4(), company_name="Example Co", job_title="AI Agent Product Manager",
        saved_jd="AI Agent workflow and knowledge management.",
    )

    result = CompanyRoleResearchSkill(provider, fetcher=fetcher)._research_company_profile(request)

    assert result[-1]["search_count"] <= 3
    assert len(fetcher.calls) <= 6
    assert len(result[-1]["rounds"]) <= 3


def test_profile_provenance_accumulates_sources_across_rounds(monkeypatch):
    stored = {}
    round_one = [
        WebSearchSource(title="Example About", url="https://example.com/about", source_type="official"),
        WebSearchSource(title="Example investor business", url="https://ir.example.com/business", source_type="official"),
        WebSearchSource(title="Example products", url="https://example.com/products", source_type="official"),
    ]
    round_two = [
        WebSearchSource(title="ExampleOS platform", url="https://example.com/platform", source_type="official"),
        WebSearchSource(title="Example AI ecosystem", url="https://example.com/ecosystem", source_type="official"),
    ]
    provider = QueryProvider([round_one, round_two])
    fetcher = ContentFetcher({
        "https://example.com/about": "Example Co company overview serves consumer markets.",
        "https://ir.example.com/business": "Example Co core business includes devices and digital services products.",
        "https://example.com/products": "Example Co products include Example Phone and Example Home devices.",
        "https://example.com/platform": "Example Co AI Agent platform and operating system support cross-device workflows.",
        "https://example.com/ecosystem": "Example Co AI assistant ecosystem connects IoT devices and knowledge services.",
    })
    monkeypatch.setattr(skill_module.company_profiles_repo, "get", lambda db, key: stored.get(key))

    def upsert(db, key, values):
        stored[key] = SimpleNamespace(**values)
        return stored[key]

    monkeypatch.setattr(skill_module.company_profiles_repo, "upsert", upsert)
    skill = CompanyRoleResearchSkill(
        provider, fetcher=fetcher, generator=UnavailableGenerator(),
        profile_generator=StaticProfileGenerator(), use_cached_profile=True,
    )

    result = skill.run(FakeDb(), uuid4(), application(job_description="AI Agent workflow and cross-device assistant"))
    provenance = stored["example"].source_provenance

    assert len(provenance["research_rounds"]) == 2
    assert len(provenance["sources"]) == 5
    assert len(result.company_knowledge_sources) == 5
    assert provenance["retrieval_diagnostics"]["search_count"] == 2
    assert provenance["retrieval_diagnostics"]["fetch_attempt_count"] == 5


def test_profile_source_selection_prefers_complementary_official_categories():
    sources = [
        WebSearchSource(title="Example phone product", url="https://example.com/phone", source_type="official"),
        WebSearchSource(title="Example About", url="https://example.com/about", source_type="official"),
        WebSearchSource(title="Example annual report", url="https://ir.example.com/annual-report", source_type="official"),
        WebSearchSource(title="ExampleOS ecosystem", url="https://developer.example.com/platform", source_type="official"),
        WebSearchSource(title="Example tablet product", url="https://example.com/tablet", source_type="official"),
    ]

    selected = CompanyRoleResearchSkill._select_company_profile_sources(sources, limit=4)

    assert [CompanyRoleResearchSkill._company_profile_source_category(item) for item in selected] == [
        "overview", "investor", "platform_ecosystem", "strategic_product",
    ]
    assert len(selected) == 4


def test_profile_product_normalization_dedupes_families_and_deprioritizes_old_models():
    draft = CompanyProfileDraft(
        positioning="Example is a technology company.",
        key_brands=["Xiaomi", "小米", "REDMI", "Redmi"],
        key_products=[
            "小米电视", "小米电视系列", "小米电视6 OLED 65英寸",
            "小米电视 大师 77” OLED",
            "小米平板", "小米平板5 Pro 12.4英寸", "Xiaomi SU7",
        ],
    )

    normalized = normalize_profile_draft(draft)

    assert normalized.key_brands == ["Xiaomi", "REDMI"]
    assert normalized.key_products == ["小米电视", "小米平板", "Xiaomi SU7"]


def test_stale_cached_profile_is_returned_without_automatic_refresh(monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(days=31)
    profile = SimpleNamespace(
        positioning="Known profile", business_lines=[], key_brands=[], key_products=[],
        customer_groups=[], strategic_focus=[], comparable_products=[], interview_notes=[],
        source_provenance={"retrieval_attempted": True, "sources": [], "fields": {}},
        generated_at=old, refreshed_at=old,
    )
    profile_generator = StaticProfileGenerator()
    monkeypatch.setattr(skill_module.company_profiles_repo, "get", lambda db, key: profile)
    result = CompanyRoleResearchSkill(
        StaticProvider(), generator=UnavailableGenerator(), profile_generator=profile_generator,
        use_cached_profile=True,
    ).run(FakeDb(), uuid4(), application())

    assert result.company_profile_is_stale is True
    assert result.company_profile_cache_hit is True
    assert profile_generator.calls == 0


def test_company_knowledge_is_jd_specific_and_contains_no_interview_answers():
    profile = SimpleNamespace(
        positioning="A consumer technology company.",
        business_lines=["Smart devices", "Digital services"],
        key_brands=["Example"],
        key_products=["ExampleOS", "Example Store"],
        customer_groups=["Consumers"],
        strategic_focus=["AI / Agent product capabilities", "Generic smartphone performance", "Commerce channel growth"],
        comparable_products=[], interview_notes=[],
    )
    ai_request = CompanyRoleResearchInput(
        application_id=uuid4(), company_name="Example", job_title="AI Agent Product Manager",
        saved_jd="Design Agent workflows, tool calling, knowledge context and cross-device experiences.",
    )
    commerce_request = ai_request.model_copy(update={
        "job_title": "E-commerce Operations",
        "saved_jd": "Own channel growth, conversion and commerce operations.",
    })

    ai_products = [RoleRelevantProductItem(
        name="ExampleOS Agent platform", type="platform",
        relevance_to_role="The JD requires Agent workflow design on ExampleOS.",
        key_scenarios=["ExampleOS task orchestration"],
        things_to_understand=["ExampleOS capability boundary", "ExampleOS tool access"],
    )]
    commerce_products = [RoleRelevantProductItem(
        name="Example Store", type="product",
        relevance_to_role="The JD owns commerce conversion in Example Store.",
        key_scenarios=["Store conversion"],
        things_to_understand=["Channel funnel", "Conversion metrics"],
    )]
    ai_knowledge = CompanyRoleResearchSkill._build_company_knowledge(profile, ai_request, generated_role_products=ai_products)
    commerce_knowledge = CompanyRoleResearchSkill._build_company_knowledge(profile, commerce_request, generated_role_products=commerce_products)

    assert ai_knowledge.role_relevant_products_and_scenarios
    assert all(item.relevance_to_role and item.things_to_understand for item in ai_knowledge.role_relevant_products_and_scenarios)
    assert any("Agent" in item.name or "OS" in item.name for item in ai_knowledge.role_relevant_products_and_scenarios)
    assert all("smartphone performance" not in item.name for item in ai_knowledge.role_relevant_products_and_scenarios)
    assert commerce_knowledge.role_relevant_products_and_scenarios[0].name == "Example Store"
    assert ai_knowledge.role_relevant_products_and_scenarios != commerce_knowledge.role_relevant_products_and_scenarios
    assert set(ai_knowledge.model_dump()) == {
        "company_positioning", "core_business", "key_brands_and_products",
        "customer_and_market", "role_relevant_products_and_scenarios", "comparable_products",
    }
    serialized = ai_knowledge.model_dump_json()
    assert "likely_questions" not in serialized
    assert "answer_strategy" not in serialized
    assert "reference_answer" not in serialized


def test_company_research_prefers_application_job_description(monkeypatch):
    app = application(job_id=uuid4(), job_description="Application JD snapshot")
    monkeypatch.setattr(
        skill_module.jobs_repo,
        "get_row",
        lambda db, user_id, job_id: SimpleNamespace(description="Linked Job JD"),
    )

    result = CompanyRoleResearchSkill(
        StaticProvider(),
        generator=UnavailableGenerator(),
    ).run(object(), app.user_id, app)

    saved_jd = next(item for item in result.evidence if item.source_id == "source_saved_jd")
    assert saved_jd.text == "Application JD snapshot"


def test_unauthorized_application_is_not_exposed(monkeypatch):
    monkeypatch.setattr(applications_api, "ensure_user", lambda db, user_id: None)
    monkeypatch.setattr(applications_api.applications_repo, "get", lambda db, user_id, application_id: None)

    with pytest.raises(HTTPException) as exc:
        applications_api.research_company_and_role(uuid4(), object(), uuid4())

    assert exc.value.status_code == 404
    assert exc.value.detail["error"]["code"] == "APPLICATION_NOT_FOUND"


def test_missing_saved_jd_returns_unavailable(monkeypatch):
    app = application(job_id=uuid4())
    monkeypatch.setattr(skill_module.jobs_repo, "get_row", lambda db, user_id, job_id: SimpleNamespace(description=None))

    result = CompanyRoleResearchSkill(
        StaticProvider(),
        generator=UnavailableGenerator(),
    ).run(object(), app.user_id, app)

    assert result.role_decoder.status == "unavailable"
    assert result.role_decoder.items == []


def test_provider_without_sources_never_invents_external_sections():
    app = application()
    result = CompanyRoleResearchSkill(
        StaticProvider(),
        generator=UnavailableGenerator(),
    ).run(object(), app.user_id, app)

    assert result.recent_signals.status == "unavailable"
    assert result.competitive_context.status == "unavailable"
    assert result.likely_interview_focus.status == "unavailable"
    assert result.why_company_why_role_60s.status == "unavailable"
    assert result.reverse_questions.status == "unavailable"


def test_structured_output_keeps_search_snippet_out_of_report_facts(monkeypatch):
    app = application(job_id=uuid4())
    monkeypatch.setattr(skill_module.jobs_repo, "get_row", lambda db, user_id, job_id: SimpleNamespace(description="Saved JD"))
    source = WebSearchSource(
        source_type="official",
        title="Official newsroom",
        url="https://example.com/news",
        snippet="A search result snippet, not a verified report fact.",
        published_at="2026-09-01",
    )

    payload = CompanyRoleResearchSkill(
        StaticProvider(news=[source]),
        fetcher=UnavailableFetcher(),
        generator=UnavailableGenerator(),
    ).run(object(), app.user_id, app).model_dump(mode="json")

    assert set(payload) == {
        "application_id", "company_name", "job_title", "company_map", "role_decoder",
        "recent_signals", "competitive_context", "likely_interview_focus",
            "why_company_why_role_60s", "reverse_questions", "sources",
            "fetched_sources", "evidence", "interview_references", "generation_status",
            "company_profile_generated_at", "company_profile_refreshed_at",
            "company_profile_is_stale", "company_profile_cache_hit",
            "company_knowledge",
            "company_knowledge_source_ids", "company_knowledge_sources",
        }
    assert payload["recent_signals"]["status"] == "unavailable"
    assert payload["recent_signals"]["items"] == []
    assert any(item["url"] == "https://example.com/news" for item in payload["sources"])


def test_source_type_and_external_url_validation():
    with pytest.raises(ValidationError):
        SourceMetadata(source_type="web", title="Invalid source")
    with pytest.raises(ValidationError):
        SourceMetadata(source_type="external", title="Missing URL")
    with pytest.raises(ValidationError):
        WebSearchSource(
            source_type="user_provided",
            title="Invalid web source",
            url="https://example.com",
        )
    with pytest.raises(ValidationError):
        SourceMetadata(source_type="community", title="Missing community URL")


def test_unavailable_fallback_contains_no_claims():
    result = CompanyRoleResearchSkill(
        StaticProvider(),
        generator=UnavailableGenerator(),
    ).run(object(), uuid4(), application())

    for section in (
        result.role_decoder,
        result.recent_signals,
        result.competitive_context,
        result.likely_interview_focus,
        result.why_company_why_role_60s,
        result.reverse_questions,
    ):
        assert section.status == "unavailable"
        assert section.items == []


def test_supply_diagnostics_follow_section_routing_without_raw_content():
    official = WebSearchSource(
        source_type="official", title="Official", url="https://example.com/about",
    )
    news = WebSearchSource(
        source_type="external", title="News", url="https://yicai.com/story", published_at="2026-10-01",
    )
    fetched = [
        FetchedSource(
            source_id="source_official", title=official.title, url=official.url,
            source_type="official", fetch_status="unavailable", error="http_error",
        ),
        FetchedSource(
            source_id="source_news", title=news.title, url=news.url,
            source_type="external", published_at=news.published_at, content_type="text/html",
            extracted_text="redacted", fetch_status="success",
        ),
    ]
    evidence = [
        Evidence(
            evidence_id="ev_company", source_id="source_news", source_type="external",
            evidence_type="company", text="Example 公司提供企业产品服务，当前重点投入 AI。",
        ),
        Evidence(
            evidence_id="ev_recent", source_id="source_news", source_type="external",
            evidence_type="recent_signal", text="Example 公司发布 AI 产品。",
        ),
        Evidence(
            evidence_id="ev_competitive", source_id="source_news", source_type="external",
            evidence_type="competitive", text="Example 公司与 Other Agent 平台提供工作流能力。",
        ),
    ]

    diagnostics = CompanyRoleResearchSkill._build_supply_diagnostics(
        official_sources=[official], news_sources=[news], competitive_sources=[news], selected_sources=[official, news],
        fetched_sources=fetched, evidence=evidence,
    )

    assert diagnostics["company_map"]["discovered_candidate_count"] == 2
    assert diagnostics["company_map"]["fetch_attempt_count"] == 2
    assert diagnostics["company_map"]["fetch_success_count"] == 1
    assert diagnostics["recent_signals"]["extracted_evidence_count"] == 1
    assert diagnostics["competitive_context"]["extracted_evidence_count"] == 1
    assert "text" not in diagnostics["company_map"]


def test_company_fetch_selection_prefers_distinct_high_value_official_categories():
    sources = [
        WebSearchSource(title="Company products", url="https://example.com/products", source_type="official"),
        WebSearchSource(title="More products", url="https://example.com/products/more", source_type="official"),
        WebSearchSource(title="About the company", url="https://example.com/about", source_type="official"),
    ]

    selected = CompanyRoleResearchSkill._select_fetch_sources(
        official_sources=sources,
        recruitment_sources=[],
        news_sources=[],
        competitive_sources=[],
        community_sources=[],
    )

    assert [item.url for item in selected] == [
        "https://example.com/about",
        "https://example.com/products",
    ]


def test_fetch_failure_diagnostics_use_safe_stable_reason_buckets():
    failures = [
        FetchedSource(source_id="1", title="a", url="https://a.example", source_type="official", fetch_status="failed", error="timeout"),
        FetchedSource(source_id="2", title="b", url="https://b.example", source_type="official", fetch_status="skipped", error="unsupported_content_type"),
        FetchedSource(source_id="3", title="c", url="https://c.example", source_type="official", fetch_status="failed", error="http_403"),
        FetchedSource(source_id="4", title="d", url="https://d.example", source_type="official", fetch_status="unavailable", error="insufficient_content"),
    ]

    counts = CompanyRoleResearchSkill._fetch_failure_reason_counts(failures)

    assert counts["timeout"] == 1
    assert counts["non_html"] == 1
    assert counts["blocked_or_captcha"] == 1
    assert counts["dynamic_page_unreadable"] == 1


def test_competitor_handoff_binds_candidate_source_to_reference_and_target_evidence(caplog):
    fetched = FetchedSource(
        source_id="source_oppo", title="OPPO AI", url="https://oppo.com/ai",
        source_type="external", fetch_status="success", extracted_text="redacted",
    )
    evidence = [
        Evidence(
            evidence_id="ev_reference", source_id="source_oppo", source_type="external",
            evidence_type="competitive", text="OPPO Agent 平台支持工作流编排。",
        ),
        Evidence(
            evidence_id="ev_target", source_id="source_saved_jd", source_type="user_provided",
            evidence_type="role", text="岗位负责 Agent 平台和工作流编排。",
        ),
    ]
    bindings = CompanyRoleResearchSkill._build_competitive_candidate_bindings(
        candidate_metadata={
            "https://oppo.com/ai": CompetitiveCandidateMetadata(
                entity="OPPO", candidate_type="comparable_product_candidate",
                shared_dimensions=("AI assistant / Agent platform", "task orchestration"),
                official_evidence_count=1, third_party_evidence_count=0, final_priority=0,
            ),
        },
        fetched_sources=[fetched],
        evidence=evidence,
    )
    assert bindings == [{
        "entity": "OPPO",
        "candidate_type": "comparable_product_candidate",
        "candidate_category": "same_agent_platform",
        "shared_dimensions": ["AI assistant / Agent platform", "task orchestration"],
        "reference_side_evidence_ids": ["ev_reference"],
        "target_side_evidence_ids": ["ev_target"],
    }]
    assert "candidate_routed_to_generator" in caplog.text
    assert "evidence_ids_available_to_generator_count\":2" in caplog.text


@pytest.mark.parametrize(("title", "url", "body", "expected_method"), [
    ("Coze Agent Platform", "https://example.com/article", "Agent 平台支持工作流编排。", "source_title_match"),
    ("Agent Platform", "https://coze.com/docs", "Agent 平台支持工作流编排。", "canonical_url/domain_match"),
    ("Agent Platform", "https://example.com/article", "Coze 支持 Agent 工作流编排。", "extracted_entity_alias_match"),
])
def test_competitor_reference_requires_deterministic_candidate_entity_match(
    title, url, body, expected_method, caplog,
):
    fetched = FetchedSource(
        source_id="source_coze", title=title, url=url,
        source_type="external", fetch_status="success", extracted_text="redacted",
    )
    reference = Evidence(
        evidence_id="ev_reference", source_id=fetched.source_id, source_type="external",
        evidence_type="competitive", text=body,
    )
    target = Evidence(
        evidence_id="ev_target", source_id="source_saved_jd", source_type="user_provided",
        evidence_type="role", text="岗位负责 Agent 平台和工作流编排。",
    )
    bindings = CompanyRoleResearchSkill._build_competitive_candidate_bindings(
        candidate_metadata={url: CompetitiveCandidateMetadata(
            entity="Coze", candidate_type="comparable_product_candidate",
            shared_dimensions=("AI assistant / Agent platform", "task orchestration"),
            official_evidence_count=1, third_party_evidence_count=0, final_priority=0,
        )},
        fetched_sources=[fetched], evidence=[reference, target],
    )
    assert bindings[0]["reference_side_evidence_ids"] == ["ev_reference"]
    assert f'"evidence_entity_match_method":"{expected_method}"' in caplog.text
    assert '"evidence_entity_match_count":1' in caplog.text
    assert '"generator_bound_reference_evidence_ids":["ev_reference"]' in caplog.text
    assert '"generator_bound_target_evidence_ids":["ev_target"]' in caplog.text
    if expected_method != "extracted_entity_alias_match":
        assert reference.text.startswith(f"{title}.")


def test_competitor_without_specific_entity_match_is_skipped_before_generation(caplog):
    fetched = FetchedSource(
        source_id="source_generic", title="Agent workflow report", url="https://example.com/article",
        source_type="external", fetch_status="success", extracted_text="redacted",
    )
    evidence = [
        Evidence(
            evidence_id="ev_reference", source_id=fetched.source_id, source_type="external",
            evidence_type="competitive", text="Agent 平台支持工作流编排。",
        ),
        Evidence(
            evidence_id="ev_target", source_id="source_saved_jd", source_type="user_provided",
            evidence_type="role", text="岗位负责 Agent 平台和工作流编排。",
        ),
    ]
    bindings = CompanyRoleResearchSkill._build_competitive_candidate_bindings(
        candidate_metadata={fetched.url: CompetitiveCandidateMetadata(
            entity="Coze", candidate_type="comparable_product_candidate",
            shared_dimensions=("AI assistant / Agent platform", "task orchestration"),
            official_evidence_count=0, third_party_evidence_count=1, final_priority=0,
        )},
        fetched_sources=[fetched], evidence=evidence,
    )
    assert bindings == []
    assert '"reference_evidence_count":1' in caplog.text
    assert '"evidence_entity_match_count":0' in caplog.text
    assert '"evidence_entity_match_method":"no_specific_match"' in caplog.text
    assert '"action":"candidate_skipped_missing_specific_reference"' in caplog.text


def test_product_level_interview_references_do_not_replace_strict_sections(caplog):
    report = unavailable_report()
    report.company_map = CompanyMapSection.model_validate({
        "status": "available",
        "items": [{
            "category": "company_positioning",
            "text": "目标公司提供面向消费者的智能设备与软件服务。",
            "claim_type": "fact",
            "evidence_ids": ["company_1"],
        }],
    })
    report.role_decoder = RoleDecoderSection.model_validate({
        "status": "available",
        "items": [{
            "category": "role_goal",
            "text": "岗位需要把 AI 能力转化为可使用的产品功能。",
            "claim_type": "inference",
            "evidence_ids": ["role_1"],
        }],
    })
    request = CompanyRoleResearchInput(
        application_id=uuid4(), company_name="目标公司", job_title="AI Agent 产品经理",
        saved_jd="负责跨设备 AI 助手、任务编排和 Skill 产品设计。",
    )
    fallbacks = CompanyRoleResearchSkill._build_interview_references(
        request=request,
        report=report,
        candidate_bindings=[{
            "entity": "Example Assistant",
            "shared_dimensions": ["AI assistant", "cross-device AI"],
        }],
    )

    assert fallbacks.recent_signals_status == "interview_reference"
    assert all("最近发布" not in item.watch_topic for item in fallbacks.recent_signals)
    assert fallbacks.competitive_context_status == "interview_reference"
    assert fallbacks.competitive_context[0].reference_type == "comparable_product"
    assert "直接竞品" not in fallbacks.competitive_context[0].why_relevant
    assert fallbacks.why_company_role_status == "interview_reference"
    assert "我的经历" not in fallbacks.why_company_role.sample_answer
    assert "我非常适合" not in fallbacks.why_company_role.sample_answer
    assert "fallback_reason\":\"insufficient_recent_grounding" in caplog.text


def test_strict_available_sections_do_not_emit_interview_reference_fallbacks():
    report = unavailable_report()
    report.recent_signals = report.recent_signals.model_validate({
        "status": "available",
        "items": [{
            "title": "目标公司发布新的 AI 产品能力",
            "why_it_matters_for_interview": "这与岗位的产品设计职责直接相关。",
            "role_relevance": "high",
            "claim_type": "fact",
            "evidence_ids": ["recent_1"],
        }],
    })
    request = CompanyRoleResearchInput(
        application_id=uuid4(), company_name="目标公司", job_title="AI 产品经理",
    )
    fallbacks = CompanyRoleResearchSkill._build_interview_references(
        request=request, report=report, candidate_bindings=[],
    )
    assert fallbacks.recent_signals_status == "unavailable"
    assert fallbacks.recent_signals == []
