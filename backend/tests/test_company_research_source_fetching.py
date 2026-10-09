from datetime import date
import socket

import httpx
import pytest
from pydantic import ValidationError

from app.skills.company_role_research.evidence import EvidenceExtractor, clean_html_text
from app.skills.company_role_research.fetcher import SourceFetcher
from app.skills.company_role_research.schemas import CompanyRoleResearchInput, Evidence, FetchedSource, WebSearchSource
from app.skills.company_role_research.skill import CompanyRoleResearchSkill
from app.skills.company_role_research.generator import GenerationOutcome, unavailable_report
from app.skills.company_role_research.competitive_discovery import CompetitiveCandidateMetadata
from tests.test_company_role_research_skill import StaticProvider, application


def source(url="https://example.com/article", source_type="official", title="Example"):
    return WebSearchSource(title=title, url=url, source_type=source_type)


def public_resolver(host, port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def fetcher(handler, **kwargs):
    return SourceFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        resolver=public_resolver,
        **kwargs,
    )


def test_successful_html_fetch_extracts_chinese_and_removes_noise():
    html = """
    <html><head><title>示例科技校园招聘</title><style>.x{}</style></head>
    <body><header>顶部导航</header><nav>职位 首页</nav>
      <main><h1>示例科技校园招聘</h1><p>面向应届毕业生开放产品经理岗位，候选人将参与用户研究、产品规划与跨团队协作。</p>
      <p>本次招聘包含线上申请、笔试和面试环节，具体时间以公司招聘官网通知为准。</p>
      <div class="recommend-list"><p>无关推荐文章</p></div></main>
      <script>secret()</script><footer>页脚信息</footer>
    </body></html>
    """

    result = fetcher(lambda request: httpx.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode(),
    )).fetch_source(source())

    assert result.fetch_status == "success"
    assert "示例科技校园招聘" in result.extracted_text
    assert "产品经理岗位" in result.extracted_text
    assert "顶部导航" not in result.extracted_text
    assert "无关推荐文章" not in result.extracted_text
    assert "secret" not in result.extracted_text


def test_clean_html_text_honors_length_limit():
    assert len(clean_html_text(f"<main><p>{'内容' * 100}</p></main>", max_length=50)) == 50


def test_timeout_and_http_errors_are_isolated():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    assert fetcher(timeout).fetch_source(source()).error == "timeout"

    for status in (404, 503):
        result = fetcher(lambda request, status=status: httpx.Response(status)).fetch_source(source())
        assert result.fetch_status == "failed"
        assert result.error == f"http_{status}"


def test_unsupported_content_type_and_oversized_response_are_skipped():
    pdf = fetcher(lambda request: httpx.Response(
        200,
        headers={"content-type": "application/pdf"},
        content=b"pdf",
    )).fetch_source(source())
    assert pdf.fetch_status == "skipped"
    assert pdf.error == "unsupported_content_type"

    oversized = fetcher(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 11,
        ),
        max_response_bytes=10,
    ).fetch_source(source())
    assert oversized.fetch_status == "skipped"
    assert oversized.error == "response_too_large"


@pytest.mark.parametrize("url", [
    "http://localhost/page",
    "http://127.0.0.1/page",
    "http://10.0.0.1/page",
    "http://169.254.1.1/page",
    "file:///etc/passwd",
    "ftp://example.com/file",
])
def test_ssrf_and_unsupported_schemes_are_rejected_without_request(url):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200)

    result = fetcher(handler).fetch_source(source(url))

    assert result.fetch_status == "skipped"
    assert requests == []


def test_redirect_destination_is_validated_again():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})

    result = fetcher(handler).fetch_source(source())

    assert result.fetch_status == "skipped"
    assert result.error == "redirect_rejected"
    assert len(requests) == 1


def test_empty_body_is_unavailable_and_never_uses_search_snippet():
    candidate = WebSearchSource(
        title="Search title",
        url="https://example.com/empty",
        source_type="external",
        snippet="This must not become evidence.",
    )
    result = fetcher(lambda request: httpx.Response(
        200,
        headers={"content-type": "text/html"},
        content=b"<html><script>only noise</script></html>",
    )).fetch_source(candidate)

    assert result.fetch_status == "unavailable"
    assert result.extracted_text == ""
    assert "snippet" not in result.model_dump()


def test_dynamic_shell_with_insufficient_public_text_is_unavailable():
    result = fetcher(lambda request: httpx.Response(
        200,
        headers={"content-type": "text/html"},
        content="<html><head><title>招聘</title></head><body><div id='app'></div></body></html>".encode(),
    )).fetch_source(source())

    assert result.fetch_status == "unavailable"
    assert result.error == "insufficient_content"


def test_community_source_can_only_create_interview_evidence():
    fetched = FetchedSource(
        source_id="source_community",
        title="面经",
        url="https://nowcoder.com/discuss/1",
        source_type="community",
        content_type="text/html",
        extracted_text="示例科技公司战略与财务增长情况。\n产品经理一面主要讨论了用户需求分析。",
        fetch_status="success",
    )

    evidence = EvidenceExtractor().extract(
        fetched,
        company_name="示例科技",
        job_title="产品经理",
    )

    assert evidence
    assert {item.evidence_type for item in evidence} == {"interview_experience"}
    assert all(item.source_type == "community" for item in evidence)
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="invalid",
            source_id="source_community",
            source_type="community",
            evidence_type="company",
            text="Community content cannot become a company fact.",
        )


def test_ai_agent_product_update_is_extracted_as_recent_signal():
    fetched = FetchedSource(
        source_id="source_ai_news",
        title="AI 产品动态",
        url="https://infoq.cn/article/ai-agent",
        source_type="external",
        published_at="2026-10-01",
        content_type="text/html",
        extracted_text="小米大模型团队更新 AI Agent 工作流与知识管理能力，并推进办公协同场景落地。",
        fetch_status="success",
    )

    evidence = EvidenceExtractor().extract(fetched, company_name="小米", job_title="AI Agent 产品经理")

    assert "recent_signal" in {item.evidence_type for item in evidence}


def test_non_target_agent_platform_content_enters_competitive_candidate_pool():
    fetched = FetchedSource(
        source_id="source_muse",
        title="Muse Agent 平台",
        url="https://qbitai.com/muse-agent",
        source_type="external",
        published_at="2026-10-01",
        content_type="text/html",
        extracted_text="小红书 Muse 发布 Agent Team 与 Agent OS，提供 workflow orchestration 能力。",
        fetch_status="success",
    )

    evidence = EvidenceExtractor().extract(fetched, company_name="小米", job_title="AI Agent 产品经理")
    evidence_types = {item.evidence_type for item in evidence}

    assert "competitive" in evidence_types
    assert "recent_signal" in evidence_types


def test_named_agent_product_routes_to_competitive_candidate_pool():
    fetched = FetchedSource(
        source_id="source_named_agent",
        title="Hermes Agent 产品动态",
        url="https://example.com/hermes-agent",
        source_type="external",
        published_at=date.today().isoformat(),
        content_type="text/html",
        extracted_text="Hermes Agent 接入某大模型，支持云端部署和工具调用。",
        fetch_status="success",
    )

    evidence = EvidenceExtractor().extract(fetched, company_name="小米", job_title="AI Agent 产品经理")

    assert "competitive" in {item.evidence_type for item in evidence}


def test_old_comparison_source_routes_to_competitive_but_not_recent_signal():
    fetched = FetchedSource(
        source_id="source_old_comparison",
        title="公开产品对比",
        url="https://example.com/comparison",
        source_type="external",
        published_at="2020-01-01",
        content_type="text/html",
        extracted_text="公开资料对比小米 MiMo 与其他 Agent 平台的工作流编排能力和产品差异。",
        fetch_status="success",
    )

    evidence = EvidenceExtractor().extract(fetched, company_name="小米", job_title="AI Agent 产品经理")
    evidence_types = {item.evidence_type for item in evidence}

    assert "competitive" in evidence_types
    assert "recent_signal" not in evidence_types


def test_recent_publication_can_route_to_recent_signal():
    fetched = FetchedSource(
        source_id="source_recent_xiaomi",
        title="小米 Agent 更新",
        url="https://example.com/xiaomi-agent",
        source_type="external",
        published_at=date.today().isoformat(),
        content_type="text/html",
        extracted_text="小米发布 MiMo Agent 工作流能力更新。",
        fetch_status="success",
    )

    evidence = EvidenceExtractor().extract(fetched, company_name="小米", job_title="AI Agent 产品经理")

    assert "recent_signal" in {item.evidence_type for item in evidence}


class SameEventFetcher:
    def __init__(self, readable_urls):
        self.readable_urls = readable_urls
        self.calls = []

    def fetch_source(self, candidate):
        self.calls.append(candidate.url)
        if candidate.url not in self.readable_urls:
            return FetchedSource(
                source_id="source_dynamic", title=candidate.title, url=candidate.url,
                source_type=candidate.source_type, published_at=candidate.published_at,
                content_type="text/html", fetch_status="unavailable", error="insufficient_content",
            )
        return FetchedSource(
            source_id="source_alternative", title=candidate.title, url=candidate.url,
            source_type=candidate.source_type, published_at=candidate.published_at,
            content_type="text/html",
            extracted_text="小米发布 MiMo-V2.5-Pro Agent 工作流产品更新，并推进知识管理场景。",
            fetch_status="success",
        )


def recent_candidate(title, url, published_at=None):
    return WebSearchSource(
        title=title, url=url, source_type="external",
        published_at=published_at or date.today().isoformat(),
    )


def test_dynamic_recent_source_uses_readable_same_event_alternative_with_own_identity():
    dynamic = recent_candidate("小米发布 MiMo-V2.5-Pro", "https://36kr.com/dynamic")
    alternative = recent_candidate("Xiaomi MiMo-V2.5-Pro release", "https://stcn.com/readable")
    fetch = SameEventFetcher({alternative.url})
    skill = CompanyRoleResearchSkill(StaticProvider(), fetcher=fetch, generator=UnavailableGenerator())
    fetched = [FetchedSource(
        source_id="source_dynamic", title=dynamic.title, url=dynamic.url,
        source_type="external", published_at=dynamic.published_at,
        content_type="text/html", fetch_status="unavailable", error="insufficient_content",
    )]
    evidence = []
    selected = [dynamic]
    provider_sources = [dynamic]

    diagnostics = skill._try_recent_same_event_fallback(
        request=CompanyRoleResearchInput(
            application_id=application().id, company_name="小米", job_title="AI Agent 产品经理",
        ),
        selected_sources=selected,
        fetched_sources=fetched,
        evidence=evidence,
        provider_sources=provider_sources,
        recent_candidate_pool=[dynamic, alternative],
    )

    assert diagnostics["same_event_alternative_found"] == 1
    assert diagnostics["same_event_alternative_fetch_success"] == 1
    recent = next(item for item in evidence if item.evidence_type == "recent_signal")
    assert recent.source_id == "source_alternative"
    assert fetched[-1].published_at == alternative.published_at
    assert "MiMo-V2.5-Pro" in recent.text
    assert alternative in provider_sources


def test_dynamic_recent_source_without_same_event_alternative_is_dropped():
    dynamic = recent_candidate("小米发布 MiMo-V2.5-Pro", "https://36kr.com/dynamic")
    different = recent_candidate("小米发布 HyperOS 手机功能", "https://stcn.com/different")
    skill = CompanyRoleResearchSkill(StaticProvider(), fetcher=SameEventFetcher({different.url}), generator=UnavailableGenerator())
    fetched = [FetchedSource(
        source_id="source_dynamic", title=dynamic.title, url=dynamic.url, source_type="external",
        published_at=dynamic.published_at, fetch_status="unavailable", error="insufficient_content",
    )]
    evidence = []

    diagnostics = skill._try_recent_same_event_fallback(
        request=CompanyRoleResearchInput(application_id=application().id, company_name="小米", job_title="AI Agent 产品经理"),
        selected_sources=[dynamic], fetched_sources=fetched, evidence=evidence,
        provider_sources=[dynamic], recent_candidate_pool=[dynamic, different],
    )

    assert diagnostics["no_same_event_alternative"] == 1
    assert evidence == []


def test_same_event_alternative_outside_window_or_without_company_anchor_is_not_used():
    dynamic = recent_candidate("小米发布 MiMo-V2.5-Pro", "https://36kr.com/dynamic")
    old = recent_candidate("Xiaomi MiMo-V2.5-Pro release", "https://stcn.com/old", "2020-01-01")
    no_anchor = recent_candidate("Xiaomi MiMo-V2.5-Pro release", "https://stcn.com/no-anchor")
    fetch = SameEventFetcher({no_anchor.url})
    skill = CompanyRoleResearchSkill(StaticProvider(), fetcher=fetch, generator=UnavailableGenerator())
    fetched = [FetchedSource(
        source_id="source_dynamic", title=dynamic.title, url=dynamic.url, source_type="external",
        published_at=dynamic.published_at, fetch_status="unavailable", error="insufficient_content",
    )]
    # The readable page body is replaced with another company's event, so it cannot become Xiaomi evidence.
    original_fetch = fetch.fetch_source
    def without_anchor(candidate):
        result = original_fetch(candidate)
        if result.fetch_status == "success":
            return result.model_copy(update={"extracted_text": "其他公司发布 MiMo-V2.5-Pro Agent 工作流产品更新。"})
        return result
    fetch.fetch_source = without_anchor
    evidence = []

    diagnostics = skill._try_recent_same_event_fallback(
        request=CompanyRoleResearchInput(application_id=application().id, company_name="小米", job_title="AI Agent 产品经理"),
        selected_sources=[dynamic], fetched_sources=fetched, evidence=evidence,
        provider_sources=[dynamic], recent_candidate_pool=[dynamic, old, no_anchor],
    )

    assert old.url not in fetch.calls
    assert diagnostics["same_event_alternative_fetch_failed"] == 1
    assert evidence == []


class PartialFetcher:
    def __init__(self):
        self.calls = []

    def fetch_source(self, candidate):
        self.calls.append(candidate.url)
        if candidate.url.endswith("failed"):
            return self.failed_result(candidate, "timeout")
        return FetchedSource(
            source_id=f"source_{len(self.calls)}",
            title=candidate.title,
            url=candidate.url,
            source_type=candidate.source_type,
            content_type="text/html",
            extracted_text="示例科技发布校园招聘计划，产品经理岗位面向应届毕业生。",
            fetch_status="success",
        )

    def failed_result(self, candidate, error="fetch_error"):
        return FetchedSource(
            source_id=f"source_{len(self.calls)}",
            title=candidate.title,
            url=candidate.url,
            source_type=candidate.source_type,
            fetch_status="failed",
            error=error,
        )


class UnavailableGenerator:
    def generate(self, **kwargs):
        return GenerationOutcome(unavailable_report(), "unavailable")


def test_duplicate_url_and_partial_failure_do_not_fail_workflow():
    duplicate = source("https://example.com/same")
    failed = source("https://example.com/failed", source_type="external")
    successful = source("https://example.com/success", source_type="campus")
    fake_fetcher = PartialFetcher()
    provider = StaticProvider(
        official=[duplicate],
        careers=[duplicate],
        news=[failed],
        campus=[successful],
    )

    result = CompanyRoleResearchSkill(
        provider,
        fetcher=fake_fetcher,
        generator=UnavailableGenerator(),
    ).run(
        object(),
        application().user_id,
        application(),
    )

    assert fake_fetcher.calls == [
        "https://example.com/same",
        "https://example.com/success",
        "https://example.com/failed",
    ]
    assert [item.fetch_status for item in result.fetched_sources] == ["success", "success", "failed"]
    assert result.evidence


def test_selected_competitor_uses_same_candidate_fallback_without_extra_search(caplog):
    primary = source("https://docs.dify.ai/dynamic", source_type="external", title="Dify Official")
    failed_alternative = source("https://docs.dify.ai/other-dynamic", source_type="external", title="Dify Docs")
    alternative = source("https://infoq.cn/dify", source_type="external", title="Dify 产品解析")

    class Provider(StaticProvider):
        def __init__(self):
            super().__init__(competitive=[primary])

        def get_competitive_candidate_metadata(self, company_name):
            return {primary.url: CompetitiveCandidateMetadata(
                entity="Dify", candidate_type="comparable_product_candidate",
                shared_dimensions=("AI assistant / Agent platform", "task orchestration"),
                official_evidence_count=1, third_party_evidence_count=1, final_priority=10,
            )}

        def get_competitive_candidate_alternatives(self, company_name):
            return {primary.url: [failed_alternative, alternative]}

    class Fetcher:
        def __init__(self):
            self.calls = []

        def fetch_source(self, item):
            self.calls.append(item.url)
            return FetchedSource(
                source_id="source_alt" if item.url == alternative.url else "source_primary",
                title=item.title, url=item.url, source_type=item.source_type,
                fetch_status="success" if item.url == alternative.url else "skipped",
                extracted_text="Dify Agent 平台支持工作流编排。" if item.url == alternative.url else "",
                error=None if item.url == alternative.url else "dynamic_page_unreadable",
            )

        def failed_result(self, item, error="fetch_error"):
            raise AssertionError("unexpected fetch exception")

    fetch = Fetcher()
    CompanyRoleResearchSkill(
        Provider(), fetcher=fetch, generator=UnavailableGenerator(),
    ).run(object(), application(job_description="负责 Agent 平台与工作流编排").user_id,
          application(job_description="负责 Agent 平台与工作流编排"))

    assert fetch.calls == [primary.url, failed_alternative.url, alternative.url]
    assert "fallback_source_found_count\":1" in caplog.text
    assert "fallback_fetch_success_count\":1" in caplog.text
    assert "reference_evidence_count\":1" in caplog.text
    assert "alternate_source_count\":2" in caplog.text
    assert "alternate_source_attempt_count\":2" in caplog.text
    assert "alternate_source_fetch_success\":1" in caplog.text
    assert "final_reference_evidence_count\":1" in caplog.text
