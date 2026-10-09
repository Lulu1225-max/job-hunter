from app.skills.company_role_research.competitive_discovery import (
    candidate_priority,
    discover_entity,
    entity_specificity_penalty,
    infer_competitive_dimensions,
    is_specific_candidate_entity,
    market_seed_terms,
    select_diverse_candidates,
)


def test_generic_product_categories_are_not_candidate_entities():
    assert discover_entity("AI Agent 平台", "AI Agent 工作流") is None
    assert discover_entity("CRM Agent 产品比较", "CRM Agent 工作流") is None
    assert discover_entity("Step by step guide", "Step AI Agent workflow") is None
    assert discover_entity("打破行业边界", "打破 AI Agent 边界") is None


def test_candidate_entity_hygiene_requires_stable_or_official_product_identity():
    assert not is_specific_candidate_entity(
        "Step", title="Step by step", has_official_source=False, stable_result_count=1,
    )
    assert not is_specific_candidate_entity(
        "打破", title="打破行业边界", has_official_source=False, stable_result_count=3,
    )
    assert is_specific_candidate_entity(
        "Dify", title="Dify Agent Platform", has_official_source=True, stable_result_count=1,
    )


def test_broad_platform_entities_remain_eligible_but_rank_below_specific_products():
    dimensions = ["AI assistant / Agent platform"]
    specific = candidate_priority(
        text="Dify official AI Agent platform", dimensions=dimensions,
        is_official_product_source=True, entity="Dify",
    )
    broad = candidate_priority(
        text="Android official AI Agent platform", dimensions=dimensions,
        is_official_product_source=True, entity="Android",
    )
    assert entity_specificity_penalty("Dify") == 0
    assert entity_specificity_penalty("Android") > 0
    assert specific is not None and broad is not None
    assert specific.final_priority < broad.final_priority
    assert [item for item, _ in select_diverse_candidates([
        ("android", broad), ("dify", specific),
    ], limit=1)] == ["dify"]


def test_device_market_peer_and_specific_assistant_outrank_generic_references():
    dimensions = ["AI assistant / Agent platform", "cross-device AI ecosystem"]
    market_context = "smartphone consumer device cross-device AI role"
    device_peer = candidate_priority(
        text="official smartphone AI assistant cross-device device ecosystem",
        dimensions=dimensions, is_official_product_source=True, entity="DeviceAssistant",
        candidate_origin="seeded", market_context=market_context,
    )
    generic_agent = candidate_priority(
        text="official generic Agent platform",
        dimensions=dimensions, is_official_product_source=True, entity="GenericAgent",
        candidate_origin="seeded", market_context=market_context,
    )
    cloud = candidate_priority(
        text="official cloud Agent platform", dimensions=dimensions,
        is_official_product_source=True, entity="Cloud",
        candidate_origin="seeded", market_context=market_context,
    )
    assert device_peer.market_candidate_type == "direct_market_peer"
    assert device_peer.qualification_status == "primary_market_peer"
    assert generic_agent.market_candidate_type == "same_agent_platform"
    assert generic_agent.qualification_status == "secondary_product_reference"
    assert cloud.market_candidate_type == "infrastructure_reference"
    assert cloud.qualification_status == "infrastructure_reference"
    assert device_peer.final_priority < generic_agent.final_priority < cloud.final_priority


def test_market_overlap_gate_rejects_events_and_orders_peer_reference_infrastructure():
    dimensions = ["AI assistant / Agent platform", "cross-device AI ecosystem"]
    market_context = "smartphone consumer smart-device ecosystem AI assistant cross-device role"
    peer = candidate_priority(
        text="official smartphone smart-device ecosystem AI assistant cross-device product",
        dimensions=dimensions, is_official_product_source=True, entity="DeviceAssistant",
        candidate_origin="seeded", market_context=market_context,
    )
    agent_only = candidate_priority(
        text="official enterprise Agent platform product",
        dimensions=dimensions, is_official_product_source=True, entity="WorkflowAgent",
        candidate_origin="seeded", market_context=market_context,
    )
    event = candidate_priority(
        text="global AI Agent conference and exhibition",
        dimensions=dimensions, is_official_product_source=True, entity="FutureAI Summit",
        candidate_origin="seeded", market_context=market_context,
    )
    infrastructure = candidate_priority(
        text="Android AI Agent platform infrastructure",
        dimensions=dimensions, is_official_product_source=True, entity="Android",
        candidate_origin="seeded", market_context=market_context,
    )

    assert event is None
    assert peer is not None and agent_only is not None and infrastructure is not None
    assert peer.entity_type in {"branded_product", "branded_platform"}
    assert peer.shared_market_dimensions == ("consumer_smart_device",)
    assert peer.shared_ai_dimensions
    assert peer.qualification_status == "primary_market_peer"
    assert agent_only.qualification_status == "secondary_product_reference"
    assert infrastructure.qualification_status == "infrastructure_reference"
    assert peer.final_priority < agent_only.final_priority < infrastructure.final_priority


def test_technology_solution_provider_without_consumer_product_is_not_primary_peer():
    candidate = candidate_priority(
        text="official IoT technical solution provider Agent platform for device makers",
        dimensions=["AI assistant / Agent platform", "cross-device AI ecosystem"],
        is_official_product_source=True, entity="DeviceTech",
        candidate_origin="seeded",
        market_context="smartphone smart-device ecosystem AI assistant cross-device role",
    )
    assert candidate is not None
    assert candidate.qualification_status == "secondary_product_reference"


def test_market_seed_terms_use_product_semantics_without_company_name_list():
    seeds = market_seed_terms(
        "AI Agent 产品经理", "负责手机 AI 助手与跨设备智能",
        ["AI assistant / Agent platform", "cross-device AI ecosystem"],
        "consumer smart device ecosystem",
    )
    joined = " ".join(seeds).casefold()
    assert "smartphone" in joined and "cross-device" in joined
    assert all(name not in joined for name in ("xiaomi", "huawei", "oppo", "vivo", "honor"))


def test_role_and_jd_infer_competitive_dimensions_without_company_hardcoding():
    dimensions = infer_competitive_dimensions(
        "AI 产品经理",
        "负责 Agent 平台、任务编排、Skill 工具体系、知识与上下文管理及跨设备协同",
    )
    assert dimensions == [
        "AI assistant / Agent platform", "cross-device AI ecosystem",
        "task orchestration", "Skill / Tool ecosystem",
    ]


def test_partner_only_integration_is_lower_priority_than_comparable_product():
    dimensions = ["AI assistant / Agent platform", "task orchestration"]
    comparable = candidate_priority(
        text="Huawei official AI assistant Agent platform and workflow",
        dimensions=dimensions, is_official_product_source=True, entity="Huawei",
    )
    partner = candidate_priority(
        text="Hermes Agent integrates model API and workflow",
        dimensions=dimensions, is_official_product_source=False, entity="Hermes Agent",
    )
    assert comparable is not None and partner is not None
    assert comparable.candidate_type == "comparable_product_candidate"
    assert partner.candidate_type == "weak_reference"
    assert comparable.final_priority < partner.final_priority


def test_terminal_ai_categories_dominate_tool_and_remote_candidates_without_company_hardcoding():
    dimensions = ["AI assistant / Agent platform", "cross-device AI ecosystem", "Skill / Tool ecosystem"]
    device = candidate_priority(
        text="official smartphone device ecosystem with cross-device AI assistant",
        dimensions=dimensions, is_official_product_source=True, entity="DeviceCo",
    )
    assistant = candidate_priority(
        text="official mobile AI assistant Agent platform",
        dimensions=dimensions, is_official_product_source=True, entity="AssistantCo",
    )
    tool = candidate_priority(
        text="official MCP tool skill service",
        dimensions=dimensions, is_official_product_source=True, entity="ToolCo",
    )
    remote = candidate_priority(
        text="AI Agent remote desktop and remote control",
        dimensions=dimensions, is_official_product_source=False, entity="RemoteCo",
    )

    assert all(candidate is not None for candidate in (device, assistant, tool, remote))
    assert device.candidate_category == "same_device_ecosystem"
    assert assistant.candidate_category == "same_ai_assistant"
    assert tool.candidate_category == "tool_only"
    assert remote.candidate_category == "remote_control"
    assert device.final_priority < assistant.final_priority < tool.final_priority < remote.final_priority
    selected = select_diverse_candidates([
        ("remote", remote), ("tool", tool), ("assistant", assistant), ("device", device),
    ], limit=2)
    assert [item for item, _ in selected] == ["device", "assistant"]


def test_terminal_ai_proximity_precedes_dimension_diversity():
    first = candidate_priority(
        text="Huawei AI assistant Agent platform", dimensions=["AI assistant / Agent platform", "task orchestration"],
        is_official_product_source=True, entity="Huawei",
    )
    duplicate = candidate_priority(
        text="OPPO AI assistant Agent platform", dimensions=["AI assistant / Agent platform", "task orchestration"],
        is_official_product_source=True, entity="OPPO",
    )
    workflow = candidate_priority(
        text="Tencent official task orchestration workflow", dimensions=["AI assistant / Agent platform", "task orchestration"],
        is_official_product_source=True, entity="Tencent",
    )
    selected = select_diverse_candidates([
        ("huawei", first), ("oppo", duplicate), ("tencent", workflow),
    ], limit=2)
    assert [item for item, _ in selected] == ["huawei", "oppo"]
