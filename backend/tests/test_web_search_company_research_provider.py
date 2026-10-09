import json

import httpx
import pytest

from app.skills.company_role_research.providers import (
    EmptyCompanyResearchProvider,
    TavilyCompanyResearchProvider,
    create_company_research_provider,
)


def _provider(handler, *, top_n=3, recent_days=90):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return TavilyCompanyResearchProvider(
        "test-api-key",
        top_n=top_n,
        recent_days=recent_days,
        client=client,
    )


def test_official_search_filters_non_official_results_and_limits_top_n():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"results": [
            {"title": "Acme — Official Site", "url": "https://www.acme.com/", "content": "Official result", "published_date": "2026-09-01"},
            {"title": "Acme on Wikipedia", "url": "https://en.wikipedia.org/wiki/Acme", "content": "Reference"},
            {"title": "Acme Group", "url": "https://acme.example/about", "content": "Another candidate"},
        ]})

    sources = _provider(handler, top_n=1).search_company_official("Acme")

    assert len(sources) == 1
    assert sources[0].url == "https://acme.example/about"
    assert sources[0].source_type == "official"
    body = json.loads(requests[0].content)
    assert requests[0].method == "POST"
    assert requests[0].headers["Authorization"] == "Bearer test-api-key"
    assert body["max_results"] == 3
    assert body["include_raw_content"] is False
    assert body["include_answer"] is False
    assert sources[0].snippet == "Another candidate"
    assert sources[0].published_at is None
    assert set(sources[0].model_dump()) == {"title", "url", "snippet", "published_at", "source_type"}


def test_profile_search_uses_dynamic_query_and_keeps_official_first():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"results": [
            {"title": "Acme Platform Official", "url": "https://developer.acme.com/platform", "content": "Platform ecosystem"},
            {"title": "Acme business report", "url": "https://stcn.com/acme", "content": "Trusted report"},
            {"title": "Acme random blog", "url": "https://unknown.example/acme", "content": "Untrusted"},
        ]})

    sources = _provider(handler).search_company_profile("Acme", "Acme official platform ecosystem")

    assert len(requests) == 1
    assert json.loads(requests[0].content)["query"] == "Acme official platform ecosystem"
    assert (sources[0].url, sources[0].source_type) == (
        "https://developer.acme.com/platform", "official",
    )
    assert ("https://stcn.com/acme", "external") in [
        (source.url, source.source_type) for source in sources
    ]


def test_profile_search_does_not_relabel_media_as_official_after_domain_discovery():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"results": [
                {"title": "Acme Official About", "url": "https://www.acme.com/about"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "Acme Agent analysis", "url": "https://blog.csdn.net/acme", "content": "Agent analysis"},
            {"title": "AcmeOS Developer", "url": "https://developer.acme.com/platform", "content": "Official platform"},
        ]})

    provider = _provider(handler)
    provider.search_company_official("Acme")
    sources = provider.search_company_profile("Acme", "Acme official Agent platform")

    assert [(source.url, source.source_type) for source in sources] == [
        ("https://developer.acme.com/platform", "official"),
    ]


def test_careers_search_is_restricted_to_identified_official_domain():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"results": [
                {"title": "Acme — Official Site", "url": "https://acme.com/"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "Join Acme", "url": "https://careers.acme.com/jobs", "content": "Open roles"},
            {"title": "Acme jobs", "url": "https://indeed.com/acme", "content": "Aggregator"},
        ]})

    provider = _provider(handler)
    provider.search_company_official("Acme")
    sources = provider.search_company_careers("Acme")

    assert calls == 2
    assert [source.url for source in sources] == ["https://careers.acme.com/jobs"]
    assert sources[0].source_type == "official"


def test_full_discovery_keeps_tavily_requests_bounded_to_five():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [
                {"title": "示例科技官网", "url": "https://example.com/about"},
            ]})
        if len(requests) == 4:
            return httpx.Response(200, json={"results": [
                {"title": "Dify Official Agent Platform", "url": "https://docs.dify.ai/product",
                 "content": "Dify Agent workflow official product"},
            ]})
        return httpx.Response(200, json={"results": []})

    provider = _provider(handler)
    provider.search_company_official("示例科技")
    provider.search_interview_experience("示例科技", "产品经理")
    provider.search_company_careers("示例科技")
    provider.search_campus_recruitment("示例科技")
    provider.search_recent_news("示例科技")
    provider.search_competitive_references("示例科技", "AI 产品经理", "负责 Agent 工作流")

    assert len(requests) == 5


def test_combined_recent_competitive_discovery_is_company_anchored_and_trusted_only():
    seen_news_request = None
    calls = 0

    def handler(request):
        nonlocal calls, seen_news_request
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"results": [
                {"title": "Acme — Official Site", "url": "https://acme.com/"},
            ]})
        seen_news_request = request
        return httpx.Response(200, json={"results": [
            {"title": "Acme update", "url": "https://acme.com/news/update", "content": "Official snippet", "published_date": "2026-09-01"},
            {"title": "Acme coverage", "url": "https://www.reuters.com/markets/acme", "content": "News snippet", "published_date": "2026-09-02"},
            {"title": "Acme rumor", "url": "https://random-blog.example/acme", "content": "Untrusted"},
        ]})

    provider = _provider(handler, recent_days=90)
    provider.search_company_official("Acme")
    sources = provider.search_recent_news("Acme")

    assert [(source.source_type, source.url) for source in sources] == [
        ("official", "https://acme.com/news/update"),
        ("external", "https://www.reuters.com/markets/acme"),
    ]
    news_body = json.loads(seen_news_request.content)
    assert news_body["topic"] == "general"
    assert news_body["max_results"] == 15
    assert news_body["query"].startswith('"Acme"')
    assert "最新" in news_body["query"] and "发布" in news_body["query"]
    assert "竞品" not in news_body["query"]
    assert "start_date" not in news_body and "end_date" not in news_body
    assert "include_domains_mode" not in news_body


def test_chinese_company_news_prioritizes_domestic_business_media():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"results": [
                {"title": "示例科技官网", "url": "https://example.cn/"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "International report", "url": "https://reuters.com/example"},
            {"title": "界面报道", "url": "https://jiemian.com/article/1"},
            {"title": "证券时报报道", "url": "https://stcn.com/article/2"},
        ]})

    provider = _provider(handler, top_n=2)
    provider.search_company_official("示例科技")
    sources = provider.search_recent_news("示例科技")

    assert [source.url for source in sources] == [
        "https://stcn.com/article/2",
        "https://jiemian.com/article/1",
    ]
    assert all(source.source_type == "external" for source in sources)


def test_ai_role_recent_news_query_is_role_aware_and_ranks_ai_signal_over_hardware():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [
                {"title": "小米官网", "url": "https://mi.com/"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "小米发布普通手机新品", "url": "https://stcn.com/mobile/1", "content": "手机发布与销量"},
            {"title": "小米更新 AI Agent 平台", "url": "https://36kr.com/p/2", "content": "大模型、工作流、Tool 与知识管理能力更新"},
        ]})

    provider = _provider(handler, top_n=2)
    provider.search_company_official("小米")
    sources = provider.search_recent_news("小米", "AI Agent 产品经理", "负责 Agent 工作流和知识管理")

    query = json.loads(requests[1].content)["query"]
    assert "AI Agent" in query and "大模型" in query and "LLM" in query and "工作流" in query
    assert query.startswith('"小米"')
    assert "最新 OR 动态 OR 发布 OR 更新" in query
    assert sources[0].title == "小米更新 AI Agent 平台"
    assert len(requests) == 2


def test_dedicated_competitor_discovery_prefers_official_and_diverse_candidates():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [
                {"title": "小米官网", "url": "https://mi.com/about"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "Huawei HarmonyOS Official", "url": "https://harmonyos.com/official",
             "content": "Huawei AI assistant cross-device ecosystem official product"},
            {"title": "OPPO 小布官方产品", "url": "https://oppo.com/xiaobu/product",
             "content": "OPPO AI 助手与跨设备终端生态官方产品"},
            {"title": "Hermes integration", "url": "https://venturebeat.com/hermes",
             "content": "Hermes Agent integrates model API and workflow"},
        ]})

    provider = _provider(handler, top_n=3)
    provider.search_company_official("小米")
    sources = provider.search_competitive_references(
        "小米", "AI Agent 产品经理", "负责 AI 助手、跨设备生态、工作流和 Skill 体系",
    )

    assert [source.title for source in sources[:2]] == [
        "Huawei HarmonyOS Official", "OPPO 小布官方产品",
    ]
    metadata = provider.get_competitive_candidate_metadata("小米")
    assert metadata[sources[0].url].official_evidence_count == 1
    assert metadata[sources[-1].url].candidate_type == "weak_reference"
    body = json.loads(requests[1].content)
    assert "smartphone brand" in body["query"]
    assert "smart device brand" in body["query"]
    assert "AI assistant" in body["query"]
    assert "cross-device AI" in body["query"]
    assert "official product" in body["query"] and "官方产品" in body["query"]
    assert "Huawei" not in body["query"] and "OPPO" not in body["query"]


def test_seeded_and_existing_search_candidates_merge_with_both_origin():
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"results": [
                {"title": "Acme Official", "url": "https://acme.com/about", "content": "smart device ecosystem"},
            ]})
        if calls == 2:
            return httpx.Response(200, json={"results": [
                {"title": "Dify Agent 平台动态", "url": "https://infoq.cn/dify", "content": "Dify Agent workflow"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "Dify Official Agent Platform", "url": "https://docs.dify.ai/product", "content": "Dify Agent workflow official"},
        ]})

    provider = _provider(handler)
    provider.search_company_official("Acme")
    provider.search_recent_news("Acme", "AI Agent 产品经理", "负责工作流编排")
    sources = provider.search_competitive_references("Acme", "AI Agent 产品经理", "负责工作流编排")
    metadata = provider.get_competitive_candidate_metadata("Acme")
    assert len(sources) == 1
    assert metadata[sources[0].url].candidate_origin == "both"
    diagnostics = provider.get_competitive_diagnostics("Acme")
    assert diagnostics["seeded_candidate_count"] == 1
    assert diagnostics["search_discovered_candidate_count"] == 1
    assert diagnostics["merged_candidate_count"] == 1


def test_unverified_seeded_candidate_is_rejected():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "Mystery Agent Platform", "url": "https://unknown.invalid/post", "content": "Agent workflow"},
        ]})
    provider = _provider(handler)
    assert provider.search_competitive_references(
        "Acme", "AI Agent 产品经理", "负责工作流编排",
    ) == []
    assert provider.get_competitive_diagnostics("Acme")["merged_candidate_count"] == 0


def test_competitor_discovery_rejects_same_industry_without_shared_dimension():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "汽车企业官方", "url": "https://car.example/official", "content": "汽车销量与门店"},
        ]})

    sources = _provider(handler).search_competitive_references(
        "示例公司", "AI Agent 产品经理", "负责知识管理与工作流",
    )
    assert sources == []


def test_competitor_discovery_rejects_title_fragments_and_keeps_same_entity_alternatives():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "Step by step AI Agent guide", "url": "https://qbitai.com/step", "content": "Agent 工作流"},
            {"title": "打破 Agent 平台边界", "url": "https://infoq.cn/break", "content": "Agent 工作流"},
            {"title": "Dify Official Agent Platform", "url": "https://docs.dify.ai/platform", "content": "Dify Agent 工作流编排官方文档"},
            {"title": "Dify 工作流产品解析", "url": "https://infoq.cn/dify", "content": "Dify Agent 工作流编排"},
        ]})

    provider = _provider(handler)
    sources = provider.search_competitive_references(
        "示例公司", "AI Agent 产品经理", "负责 Agent 平台与工作流编排",
    )

    assert [source.title for source in sources] == ["Dify Official Agent Platform"]
    alternatives = provider.get_competitive_candidate_alternatives("示例公司")
    assert [source.title for source in alternatives[sources[0].url]] == ["Dify 工作流产品解析"]
    diagnostics = provider.get_competitive_diagnostics("示例公司")
    assert diagnostics["rejected_non_entity_count"] >= 2


def test_selected_candidate_acquisition_reuses_same_entity_dimension_sources_from_pool():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "华为 AI 助手官网", "url": "https://consumer.huawei.com/ai/dynamic",
             "content": "华为 AI 助手与跨设备终端生态"},
            {"title": "HarmonyOS AI developer guide", "url": "https://developer.huawei.com/consumer/cn/doc/ai",
             "content": "HarmonyOS AI assistant cross-device ecosystem developer documentation"},
            {"title": "Huawei quarterly revenue", "url": "https://reuters.com/huawei/revenue",
             "content": "Huawei revenue and smartphone sales"},
            {"title": "Generic AI assistant", "url": "https://infoq.cn/generic-agent",
             "content": "AI assistant cross-device ecosystem"},
        ]})

    provider = _provider(handler, top_n=1)
    sources = provider.search_competitive_references(
        "小米", "AI Agent 产品经理", "负责 AI 助手与跨设备终端生态",
    )

    assert [source.title for source in sources] == ["华为 AI 助手官网"]
    alternatives = provider.get_competitive_candidate_alternatives("小米")[sources[0].url]
    assert [source.title for source in alternatives] == ["HarmonyOS AI developer guide"]


def test_top_candidate_verification_search_adds_bound_official_alternatives_only():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [
                {"title": "华为 AI 助手官网", "url": "https://consumer.huawei.com/ai/dynamic",
                 "content": "华为 AI 助手与跨设备终端生态"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "Huawei AI developer docs", "url": "https://developer.huawei.com/ai/assistant",
             "content": "Huawei AI assistant cross-device ecosystem developer documentation"},
            {"title": "Unrelated Agent guide", "url": "https://infoq.cn/other-agent",
             "content": "AI assistant cross-device ecosystem"},
            {"title": "Huawei revenue", "url": "https://reuters.com/huawei/revenue",
             "content": "Huawei quarterly revenue"},
        ]})

    provider = _provider(handler, top_n=1)
    sources = provider.search_competitive_references(
        "小米", "AI Agent 产品经理", "负责 AI 助手与跨设备终端生态",
    )

    assert len(requests) == 2
    verification_query = json.loads(requests[1].content)["query"]
    assert "华为" in verification_query
    assert "cross-device AI ecosystem" in verification_query
    alternatives = provider.get_competitive_candidate_alternatives("小米")[sources[0].url]
    assert [source.title for source in alternatives] == ["Huawei AI developer docs"]
    diagnostics = provider.get_competitive_verification_metadata("小米")[sources[0].url]
    assert diagnostics["verification_search_candidate"] == "华为"
    assert diagnostics["verification_result_count"] == 1
    assert diagnostics["verification_official_source_count"] == 1


def test_market_gate_rejects_conference_and_only_verifies_primary_peer():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [
                {"title": "DeviceMate AI Assistant Official", "url": "https://devicemate.example/product",
                 "content": "smartphone smart-device ecosystem AI assistant cross-device product"},
                {"title": "FlowAgent Official", "url": "https://flowagent.example/platform",
                 "content": "enterprise Agent platform workflow product"},
                {"title": "FutureAI Conference", "url": "https://futureai.example/conference",
                 "content": "AI Agent conference and exhibition"},
                {"title": "Android Agent Platform", "url": "https://android.example/agent",
                 "content": "Android AI Agent platform infrastructure"},
            ]})
        return httpx.Response(200, json={"results": []})

    provider = _provider(handler, top_n=3)
    sources = provider.search_competitive_references(
        "TargetCo", "AI Agent 产品经理",
        "负责 smartphone smart-device ecosystem AI assistant cross-device 产品",
    )

    metadata = provider.get_competitive_candidate_metadata("TargetCo")
    statuses = [item.qualification_status for item in metadata.values()]
    assert statuses[0] == "primary_market_peer"
    assert "infrastructure_reference" in statuses
    assert all(item.entity != "FutureAI Conference" for item in metadata.values())
    verification = provider.get_competitive_verification_metadata("TargetCo")
    assert len(verification) == 1
    assert next(iter(verification.values()))["verification_search_candidate"] == "DeviceMate"
    diagnostics = provider.get_competitive_qualification_diagnostics("TargetCo")
    assert any(item["entity_type"] == "event" and item["qualification_status"] == "reject" for item in diagnostics)
    assert sources


def test_market_first_search_discovers_diverse_device_ai_peers_without_brand_hardcoding():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [
                {"title": "AlphaPhone AI Assistant Official", "url": "https://alphaphone.example/assistant",
                 "content": "smartphone manufacturer smart-device ecosystem AI assistant cross-device product"},
                {"title": "BetaMobile AI Official", "url": "https://betamobile.example/ai",
                 "content": "mobile device company consumer device AI assistant product"},
                {"title": "SupplyTech Agent Official", "url": "https://supplytech.example/agent",
                 "content": "technical solution provider Agent platform for device makers"},
                {"title": "Future AI Conference", "url": "https://future.example/conference",
                 "content": "AI Agent conference exhibition"},
                {"title": "GenericOS Agent Platform", "url": "https://android.example/platform",
                 "content": "Android generic operating system Agent platform infrastructure"},
            ]})
        return httpx.Response(200, json={"results": []})

    provider = _provider(handler, top_n=4)
    sources = provider.search_competitive_references(
        "TargetCo", "AI Agent 产品经理",
        "负责 smartphone consumer smart-device ecosystem、AI assistant 与 cross-device AI 产品",
    )

    query = json.loads(requests[0].content)["query"]
    assert "smartphone brand" in query and "AI assistant" in query
    metadata = provider.get_competitive_candidate_metadata("TargetCo")
    primary = [item for item in metadata.values() if item.qualification_status == "primary_market_peer"]
    assert len(primary) >= 2
    assert all(item.entity_type in {"branded_product", "branded_platform"} for item in primary)
    assert any(item.qualification_status == "secondary_product_reference" for item in metadata.values())
    qualification = provider.get_competitive_qualification_diagnostics("TargetCo")
    assert any(item["entity_type"] == "event" and item["qualification_status"] == "reject" for item in qualification)
    diagnostics = provider.get_competitive_diagnostics("TargetCo")
    assert diagnostics["market_peer_search_result_count"] == 5
    assert diagnostics["primary_market_peer_count"] >= 2
    assert sources and all(source.source_type == "external" for source in sources)


def test_market_peer_entity_extraction_keeps_one_brand_not_title_fragments():
    entities = TavilyCompanyResearchProvider._extract_market_peer_entities({
        "title": "Best mobile AI assistants in 2026",
        "content": (
            "OPPO Find X brings an AI assistant to its smart-device ecosystem. "
            "This Pro model includes a new GUI and several AI features."
        ),
    })

    assert [entity for entity, _ in entities] == ["OPPO"]


def test_market_peer_entity_extraction_supports_fixture_brands_without_hardcoding():
    alpha = TavilyCompanyResearchProvider._extract_market_peer_entities({
        "title": "AlphaPhone AI Assistant Official",
        "content": "smartphone manufacturer with a cross-device AI assistant",
    })
    beta = TavilyCompanyResearchProvider._extract_market_peer_entities({
        "title": "BetaMobile AI Official",
        "content": "consumer mobile device AI assistant product",
    })

    assert [entity for entity, _ in alpha] == ["AlphaPhone"]
    assert [entity for entity, _ in beta] == ["BetaMobile"]


def test_trusted_chinese_ai_technology_sources_are_allowed_but_aggregators_are_not():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "小米 Agent 平台更新", "url": "https://qbitai.com/2026/1", "content": "AI Agent 工作流更新"},
            {"title": "小米大模型动态", "url": "https://hub.baai.ac.cn/view/2", "content": "大模型产品动态"},
            {"title": "转载聚合", "url": "https://smartcity.team/post/3", "content": "聚合内容"},
            {"title": "财富号文章", "url": "https://caifuhao.eastmoney.com/news/4", "content": "用户内容"},
        ]})

    sources = _provider(handler).search_recent_news("小米", "AI Agent 产品经理", "Agent 工作流")

    assert {source.url for source in sources} == {
        "https://qbitai.com/2026/1",
        "https://hub.baai.ac.cn/view/2",
    }


def test_official_discovery_recognizes_sibling_product_subdomain():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"results": [
                {"title": "小米官网", "url": "https://s1.mi.com/about"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "MiMo 官方模型更新", "url": "https://mimo.mi.com/news/1", "content": "小米 MiMo 更新"},
        ]})

    provider = _provider(handler)
    provider.search_company_official("小米")
    sources = provider.search_recent_news("小米", "AI Agent 产品经理", "Agent 工作流")

    assert [(source.source_type, source.url) for source in sources] == [
        ("official", "https://mimo.mi.com/news/1"),
    ]


def test_trusted_product_technology_source_can_feed_competitive_discovery():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {
                "title": "Agent 平台产品比较",
                "url": "https://adp.tencent.com/article/1",
                "content": "公开资料比较小米 MiMo 与 Agent 平台的工作流编排能力",
            },
            {"title": "个人博客转载", "url": "https://cnblogs.com/example/2", "content": "转载"},
        ]})

    sources = _provider(handler).search_recent_news("小米", "AI Agent 产品经理", "工作流编排")

    assert [(source.source_type, source.url) for source in sources] == [
        ("external", "https://adp.tencent.com/article/1"),
    ]


def test_explicit_comparison_source_is_reserved_in_top_results():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "小米 AI 新闻一", "url": "https://stcn.com/1", "content": "小米发布大模型"},
            {"title": "小米 AI 新闻二", "url": "https://yicai.com/2", "content": "小米更新 AI 产品"},
            {"title": "小米 AI 新闻三", "url": "https://caixin.com/3", "content": "小米宣布 AI 投入"},
            {
                "title": "Xiaomi MiMo Code beats Claude Code",
                "url": "https://venturebeat.com/technology/mimo-claude",
                "content": "The report compares Xiaomi MiMo Code with Anthropic Claude Code.",
            },
        ]})

    sources = _provider(handler, top_n=3).search_recent_news("小米", "AI Agent 产品经理", "工作流")

    assert "https://venturebeat.com/technology/mimo-claude" in {source.url for source in sources}


@pytest.mark.parametrize("field", ["published_at", "published_date", "date"])
def test_tavily_publication_date_aliases_are_normalized(field):
    def handler(request):
        return httpx.Response(200, json={"results": [{
            "title": "小米 AI Agent 更新",
            "url": "https://36kr.com/p/date-test",
            "content": "小米发布 AI Agent 产品",
            field: "2026-10-01T08:30:00Z",
        }]})

    source = _provider(handler).search_recent_news("小米", "AI Agent 产品经理")[0]

    assert source.published_at == "2026-10-01"


def test_recent_ranking_prefers_valid_recent_date_when_relevance_is_equal():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "小米 AI Agent 无日期", "url": "https://36kr.com/p/no-date", "content": "小米 AI Agent 工作流更新"},
            {"title": "小米 AI Agent 有日期", "url": "https://36kr.com/p/dated", "content": "小米 AI Agent 工作流更新", "published_at": "2026-10-01"},
        ]})

    sources = _provider(handler, top_n=2).search_recent_news("小米", "AI Agent 产品经理")

    assert sources[0].url == "https://36kr.com/p/dated"


def test_recent_candidate_pool_reuses_existing_tavily_response_without_new_search():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"results": [
            {"title": "小米 MiMo-V2.5 动态页", "url": "https://36kr.com/p/dynamic", "content": "小米 MiMo-V2.5 Agent 更新", "published_at": "2026-10-01"},
            {"title": "小米 MiMo-V2.5 可读报道", "url": "https://stcn.com/readable", "content": "小米 MiMo-V2.5 Agent 更新", "published_at": "2026-10-01"},
        ]})

    provider = _provider(handler, top_n=1)
    returned = provider.search_recent_news("小米", "AI Agent 产品经理")
    pool = provider.get_recent_candidate_pool("小米")

    assert len(returned) == 1
    assert len(pool) == 2
    assert len(requests) == 1


def test_campus_search_ranks_official_recruiting_above_nowcoder():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"results": [
                {"title": "示例科技官网", "url": "https://example.cn/"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "示例科技牛客校招", "url": "https://www.nowcoder.com/enterprise/1"},
            {"title": "示例科技校园招聘", "url": "https://career.example.cn/campus"},
            {"title": "聚合招聘", "url": "https://seo-jobs.example/example"},
        ]})

    provider = _provider(handler)
    provider.search_company_official("示例科技")
    sources = provider.search_campus_recruitment("示例科技")

    assert [(source.source_type, source.url) for source in sources] == [
        ("official", "https://career.example.cn/campus"),
        ("campus", "https://www.nowcoder.com/enterprise/1"),
    ]


def test_interview_experience_accepts_nowcoder_as_community_only():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"title": "示例科技产品经理面经", "url": "https://www.nowcoder.com/discuss/1"},
            {"title": "示例科技面经", "url": "https://www.zhihu.com/question/1"},
            {"title": "示例科技招聘", "url": "https://example.cn/careers"},
        ]})

    sources = _provider(handler).search_interview_experience("示例科技", "产品经理")

    assert len(sources) == 1
    assert sources[0].url == "https://www.nowcoder.com/discuss/1"
    assert sources[0].source_type == "community"


def test_provider_clamps_result_limit_and_returns_empty_on_search_error():
    requests = []

    def success(request):
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    provider = _provider(success, top_n=99)
    assert provider.search_company_official("Acme") == []
    assert json.loads(requests[0].content)["max_results"] == 15
    assert provider.top_n == 5

    def failure(request):
        return httpx.Response(503, json={"error": "unavailable"})

    assert _provider(failure).search_recent_news("Acme") == []


def test_missing_tavily_api_key_uses_empty_provider():
    assert isinstance(create_company_research_provider(None), EmptyCompanyResearchProvider)
    assert isinstance(create_company_research_provider(""), EmptyCompanyResearchProvider)
