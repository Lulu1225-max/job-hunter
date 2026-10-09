from __future__ import annotations

from dataclasses import dataclass
import re


COMPETITIVE_DIMENSION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI assistant / Agent platform", ("agent", "智能体", "ai 助手", "智能助手", "assistant")),
    ("cross-device AI ecosystem", ("跨设备", "多端", "终端生态", "cross-device", "ecosystem")),
    ("task orchestration", ("任务编排", "工作流", "workflow", "orchestration")),
    ("Skill / Tool ecosystem", ("skill", "tool", "工具调用", "技能体系", "mcp")),
    ("knowledge / context management", ("知识管理", "知识库", "上下文", "context", "rag")),
    ("office collaboration / workflow automation", ("办公协同", "流程自动化", "office", "collaboration")),
    ("enterprise AI", ("企业服务", "企业 ai", "tob", "to b", "enterprise")),
    ("developer ecosystem", ("开发者生态", "developer", "api", "sdk")),
)


@dataclass(frozen=True)
class CompetitiveCandidateMetadata:
    entity: str
    candidate_type: str
    shared_dimensions: tuple[str, ...]
    official_evidence_count: int
    third_party_evidence_count: int
    final_priority: int
    candidate_category: str = "same_agent_platform"
    partner_only: bool = False
    candidate_origin: str = "search"
    market_proximity_score: int = 0
    market_candidate_type: str = "same_agent_platform"
    verification_success: bool = True
    entity_type: str = "branded_platform"
    shared_market_dimensions: tuple[str, ...] = ()
    shared_ai_dimensions: tuple[str, ...] = ()
    market_overlap_score: int = 0
    qualification_status: str = "secondary_product_reference"


MARKET_OVERLAP_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("consumer_smart_device", (
        "smartphone", "mobile phone", "consumer device", "smart-device", "device ecosystem",
        "smart device", "iot", "智能手机", "消费电子", "智能设备", "设备生态", "终端生态", "智能家居",
    )),
    ("automotive_intelligent_cockpit", ("intelligent cockpit", "smart cockpit", "智能座舱", "车载智能")),
    ("ai_assistant", ("ai assistant", "智能助手", "ai 助手", "手机助手")),
    ("cross_device_ai", ("cross-device", "跨设备", "多端协同", "跨终端")),
    ("agent_platform", ("agent platform", "agent 平台", "智能体平台", "agent runtime")),
    ("enterprise_workflow", ("enterprise workflow", "workflow automation", "企业工作流", "流程自动化", "办公协同")),
)

CORE_MARKET_DIMENSIONS = {
    "consumer_smart_device", "automotive_intelligent_cockpit",
}
AI_MARKET_DIMENSIONS = {
    "ai_assistant", "cross_device_ai", "agent_platform", "enterprise_workflow",
}


def market_overlap_dimensions(text: str) -> tuple[str, ...]:
    normalized = text.casefold()
    return tuple(
        dimension for dimension, markers in MARKET_OVERLAP_PATTERNS
        if any(marker in normalized for marker in markers)
    )


def candidate_entity_type(entity: str, text: str, *, is_official: bool) -> str:
    normalized = f"{entity} {text}".casefold()
    if re.search(r"\bconference\b|\bsummit\b|\bexpo\b|\bexhibition\b|大会|峰会|展会|论坛|博览会", normalized):
        return "event"
    if re.search(r"\bmedia\b|新闻网|新闻社|杂志|报社", normalized) and not is_official:
        return "media"
    if entity_specificity_penalty(entity):
        return "branded_platform"
    if re.search(r"product|assistant|copilot|platform|cloud|os\b|产品|助手|平台|模型", normalized):
        return "branded_product" if not re.search(r"platform|cloud|平台|云", normalized) else "branded_platform"
    return "company"


def infer_competitive_dimensions(job_title: str | None, saved_jd: str | None) -> list[str]:
    """Deterministically derive product comparison axes from role-owned text."""
    context = f"{job_title or ''} {saved_jd or ''}".casefold()
    dimensions = [
        dimension
        for dimension, markers in COMPETITIVE_DIMENSION_PATTERNS
        if any(marker in context for marker in markers)
    ]
    if not dimensions and job_title:
        dimensions.append(job_title.strip())
    return dimensions[:4]


def shared_dimensions(text: str, dimensions: list[str]) -> list[str]:
    normalized = text.casefold()
    matches: list[str] = []
    for dimension in dimensions:
        markers = next(
            (patterns for name, patterns in COMPETITIVE_DIMENSION_PATTERNS if name == dimension),
            tuple(token for token in re.split(r"\W+", dimension.casefold()) if len(token) >= 3),
        )
        if any(marker in normalized for marker in markers):
            matches.append(dimension)
    return matches


def candidate_priority(
    *,
    text: str,
    dimensions: list[str],
    is_official_product_source: bool,
    entity: str,
    candidate_origin: str = "search",
    market_context: str = "",
) -> CompetitiveCandidateMetadata | None:
    """Classify discovery metadata only; fetched page content remains the evidence."""
    normalized = text.casefold()
    entity_type = candidate_entity_type(entity, text, is_official=is_official_product_source)
    if entity_type not in {"company", "branded_product", "branded_platform"}:
        return None
    shared = tuple(shared_dimensions(normalized, dimensions))
    if not shared:
        return None
    explicit_relation = any(marker in normalized for marker in (
        "竞品", "竞争", "对标", "替代", "对比", "比较", " versus ", " vs ",
        "competitor", "alternative", "comparison",
    ))
    partner_only = any(marker in normalized for marker in (
        "接入", "集成", "合作", "integration", "integrates", "partner", "hosted on",
    )) and not explicit_relation
    remote_control = any(marker in normalized for marker in (
        "remote control", "remote desktop", "远程控制", "远程桌面", "远程操作",
    ))
    model_hosting = any(marker in normalized for marker in (
        "model hosting", "模型托管", "模型部署", "hosted model", "inference hosting",
    ))
    has_device_context = any(marker in normalized for marker in (
        "smartphone", "mobile", "phone", "device ecosystem", "手机", "终端", "设备生态", "操作系统",
    ))
    has_assistant_context = any(marker in normalized for marker in (
        "ai assistant", "智能助手", "ai 助手", "手机助手", "assistant",
    ))
    tool_only = (
        any(marker in normalized for marker in ("tool", "skill", "mcp", "工具", "技能"))
        and not any(marker in normalized for marker in (
            "assistant", "智能助手", "ai 助手", "cross-device", "跨设备", "workflow", "工作流", "平台",
        ))
    )
    target_is_device_ai = bool(re.search(
        r"smartphone|smart.device|consumer device|手机|终端|智能设备|跨设备|cross-device",
        market_context.casefold(),
    ))
    target_overlap = set(market_overlap_dimensions(market_context))
    candidate_overlap = set(market_overlap_dimensions(text))
    shared_overlap = target_overlap & candidate_overlap
    shared_market = tuple(sorted(shared_overlap & CORE_MARKET_DIMENSIONS))
    shared_ai = tuple(sorted(shared_overlap & AI_MARKET_DIMENSIONS))
    market_overlap_score = len(shared_market) * 50 + len(shared_ai) * 20
    solution_only = bool(re.search(
        r"technical solution|technology service|solution provider|解决方案|技术服务|模组|芯片平台",
        normalized,
    )) and not bool(re.search(
        r"smartphone|mobile phone|consumer device|ai assistant|智能手机|消费电子|智能助手|ai 助手",
        normalized,
    ))
    if remote_control:
        candidate_category = "remote_control"
    elif partner_only:
        candidate_category = "partner_integration"
    elif model_hosting:
        candidate_category = "model_hosting"
    elif tool_only:
        candidate_category = "tool_only"
    elif "cross-device AI ecosystem" in shared and has_device_context:
        candidate_category = "same_device_ecosystem"
    elif "AI assistant / Agent platform" in shared and has_assistant_context:
        candidate_category = "same_ai_assistant"
    elif "cross-device AI ecosystem" in shared:
        candidate_category = "same_cross_device_ai"
    elif "AI assistant / Agent platform" in shared:
        candidate_category = "same_agent_platform"
    else:
        candidate_category = "same_enterprise_workflow"
    candidate_type = (
        "direct_competitor_candidate" if explicit_relation
        else "weak_reference" if partner_only
        else "comparable_product_candidate"
    )
    if partner_only:
        market_candidate_type = "partner_integration"
    elif remote_control or model_hosting or entity_specificity_penalty(entity):
        market_candidate_type = "infrastructure_reference"
    elif target_is_device_ai and has_device_context and has_assistant_context:
        market_candidate_type = "direct_market_peer"
    elif has_device_context:
        market_candidate_type = "same_device_ai_ecosystem"
    elif has_assistant_context:
        market_candidate_type = "same_ai_assistant"
    elif "AI assistant / Agent platform" in shared:
        market_candidate_type = "same_agent_platform"
    elif "enterprise AI" in shared or "office collaboration / workflow automation" in shared:
        market_candidate_type = "enterprise_agent_platform"
    else:
        market_candidate_type = "infrastructure_reference"
    market_scores = {
        "direct_market_peer": 100,
        "same_device_ai_ecosystem": 90,
        "same_ai_assistant": 80,
        "same_agent_platform": 65,
        "enterprise_agent_platform": 45,
        "infrastructure_reference": 15,
        "partner_integration": 5,
    }
    market_proximity_score = market_scores[market_candidate_type]
    infrastructure = bool(entity_specificity_penalty(entity)) or market_candidate_type in {
        "infrastructure_reference", "partner_integration",
    }
    if infrastructure:
        qualification_status = "infrastructure_reference"
    elif (
        len(shared_overlap) >= 2
        and shared_market
        and shared_ai
        and not solution_only
    ):
        qualification_status = "primary_market_peer"
    else:
        qualification_status = "secondary_product_reference"
    qualification_rank = {
        "primary_market_peer": 0,
        "secondary_product_reference": 100,
        "infrastructure_reference": 200,
    }[qualification_status]
    # Product-category proximity is the primary selection signal for terminal-AI
    # roles.  Candidate type and official-source quality are only tie-breakers,
    # so a same-device comparable product cannot be displaced by a remote-control
    # or model-hosting result merely because the latter says "competitor".
    type_rank = {"direct_competitor_candidate": 0, "comparable_product_candidate": 2, "weak_reference": 20}
    category_rank = {
        "same_device_ecosystem": 0,
        "same_ai_assistant": 4,
        "same_cross_device_ai": 8,
        "same_agent_platform": 12,
        "same_enterprise_workflow": 18,
        "tool_only": 55,
        "partner_integration": 60,
        "model_hosting": 65,
        "remote_control": 70,
    }
    diversity_rank = dimensions.index(shared[0]) if shared[0] in dimensions else len(dimensions)
    priority = (
        qualification_rank
        + type_rank[candidate_type]
        + category_rank[candidate_category]
        + diversity_rank * 3
        + entity_specificity_penalty(entity)
        - market_proximity_score
        - (1 if is_official_product_source else 0)
    )
    return CompetitiveCandidateMetadata(
        entity=entity,
        candidate_type=candidate_type,
        shared_dimensions=shared,
        official_evidence_count=1 if is_official_product_source else 0,
        third_party_evidence_count=0 if is_official_product_source else 1,
        final_priority=priority,
        candidate_category=candidate_category,
        partner_only=partner_only,
        candidate_origin=candidate_origin,
        market_proximity_score=market_proximity_score,
        market_candidate_type=market_candidate_type,
        verification_success=True,
        entity_type=entity_type,
        shared_market_dimensions=shared_market,
        shared_ai_dimensions=shared_ai,
        market_overlap_score=market_overlap_score,
        qualification_status=qualification_status,
    )


def market_seed_terms(
    job_title: str | None,
    saved_jd: str | None,
    dimensions: list[str],
    official_context: str = "",
) -> list[str]:
    """Create market descriptors, never a hardcoded list of company names."""
    context = f"{job_title or ''} {saved_jd or ''} {official_context}".casefold()
    terms: list[str] = []
    if "cross-device AI ecosystem" in dimensions or re.search(r"手机|终端|智能设备|跨设备|smartphone|device", context):
        terms.extend([
            "智能手机 AI 助手",
            "终端 AI 跨设备生态",
            "手机智能助手 官方产品",
            "smartphone AI assistant",
            "cross-device AI ecosystem",
        ])
    if "AI assistant / Agent platform" in dimensions:
        terms.extend(["AI assistant official product", "consumer AI Agent platform"])
    if "task orchestration" in dimensions or "Skill / Tool ecosystem" in dimensions:
        terms.extend(["Agent workflow Skill Tool official platform", "Agent orchestration official product"])
    if "enterprise AI" in dimensions or "office collaboration / workflow automation" in dimensions:
        terms.extend(["enterprise Agent workflow official platform", "AI office assistant official product"])
    return list(dict.fromkeys(terms))[:10]


def discover_entity(title: str, text: str) -> str | None:
    """Extract a specific discovery label, never a generic industry noun."""
    generic = {
        "ai", "agent", "ai agent", "llm", "crm", "crm agent", "platform", "official", "官网", "官方", "平台",
        "智能体", "大模型", "产品", "公司", "行业", "enterprise", "workflow",
        "agentic ai", "best practices", "building", "business training", "contribution list",
        "own agents", "service now", "this", "introduction", "overview", "jmedia", "keyvox",
        "国产", "我们", "国内", "精选", "顶级",
        "step", "steps", "today", "now", "break", "breaking", "new", "latest",
        "打破", "推动", "发布", "推出", "升级", "宣布", "实现", "如何", "为何",
    }
    chinese_brand = re.search(
        r"([\u3400-\u9fff]{2,5})(?=\s*(?:AI|官方网站|官网|助手|平台|智能体))",
        title,
        re.I,
    )
    if chinese_brand:
        normalized_brand = chinese_brand.group(1).casefold()
        if normalized_brand not in generic and not re.search(
            r"需要|什么|我们|如何|怎样|究竟|国产|国内|精选|顶级",
            normalized_brand,
        ):
            return chinese_brand.group(1)
    candidates = re.findall(
        r"\b[A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,2}\b|"
        r"[\u3400-\u9fff]{2,12}(?:小艺|小布|蓝心小V|YOYO|元宝|豆包)",
        f"{title} {text}",
    )
    for candidate in candidates:
        normalized = candidate.casefold().strip()
        if normalized not in generic and not any(
            marker in normalized for marker in ("best practice", "training", "contribution", "conference")
        ) and not re.match(r"^(?:step|steps|today|now|new|latest)(?:\s|$)", normalized) and len(normalized) >= 2:
            return candidate.strip()
    return None


def candidate_entity_key(entity: str) -> str:
    """Canonical key for grouping the same named product across result titles."""
    normalized = re.sub(r"[\s._-]+", " ", entity.casefold()).strip()
    normalized = re.sub(r"(?:\s+(?:official|ai|agent|platform|assistant|cloud|product))+$", "", normalized)
    return normalized.strip()


def entity_specificity_penalty(entity: str) -> int:
    """Keep broad ecosystems eligible, but behind named products and brands."""
    broad_platforms = {
        "android", "ios", "linux", "web", "cloud", "mobile", "desktop",
        "browser", "operating system", "云平台",
    }
    return 100 if candidate_entity_key(entity) in broad_platforms else 0


def is_specific_candidate_entity(
    entity: str,
    *,
    title: str,
    has_official_source: bool,
    stable_result_count: int,
) -> bool:
    """Reject title fragments while accepting evidence-backed brands/products."""
    normalized = re.sub(r"[\s._-]+", " ", entity.casefold()).strip()
    generic = {
        "ai", "agent", "ai agent", "agents", "crm", "llm", "platform", "workflow",
        "step", "steps", "today", "now", "break", "breaking", "new", "latest",
        "智能体", "平台", "产品", "公司", "打破", "推动", "发布", "推出", "升级", "宣布", "实现",
    }
    if normalized in generic or len(normalized) < 2:
        return False
    if re.fullmatch(r"[\u3400-\u9fff]{2,4}", entity) and re.search(
        r"打破|推动|发布|推出|升级|宣布|实现|需要|如何|为何|什么|最新", entity,
    ):
        return False
    title_has_entity = bool(re.search(re.escape(entity), title, re.I))
    product_shape = bool(
        re.search(r"[A-Z0-9][A-Za-z0-9._-]*(?:\s+(?:AI|Agent|Cloud|OS|Copilot|Assistant))?", entity)
        or re.search(r"(?:助手|小艺|小布|蓝心|YOYO|元宝|豆包|平台|云|模型)$", entity, re.I)
    )
    return has_official_source or stable_result_count >= 2 or (title_has_entity and product_shape)


def discovery_query_terms(dimensions: list[str]) -> list[str]:
    localized = {
        "AI assistant / Agent platform": "AI 助手 Agent 平台",
        "cross-device AI ecosystem": "智能手机 跨设备生态",
        "task orchestration": "Agent 工作流编排",
        "Skill / Tool ecosystem": "Skill Tool 工具体系",
        "knowledge / context management": "知识管理 上下文",
        "office collaboration / workflow automation": "办公协同 流程自动化",
        "enterprise AI": "企业 AI 平台",
        "developer ecosystem": "开发者生态",
    }
    return [localized.get(dimension, dimension) for dimension in dimensions[:4]]


def select_diverse_candidates(
    candidates: list[tuple[object, CompetitiveCandidateMetadata]],
    *,
    limit: int = 3,
) -> list[tuple[object, CompetitiveCandidateMetadata]]:
    """Prefer different comparison axes before adding a duplicate reference type."""
    ranked = sorted(candidates, key=lambda entry: entry[1].final_priority)
    selected: list[tuple[object, CompetitiveCandidateMetadata]] = []
    covered: set[str] = set()
    terminal_ai_categories = {
        "same_device_ecosystem", "same_ai_assistant",
        "same_cross_device_ai", "same_agent_platform",
    }
    strong = [entry for entry in ranked if entry[1].candidate_type != "weak_reference"]
    preferred = [entry for entry in strong if entry[1].candidate_category in terminal_ai_categories]
    other_strong = [entry for entry in strong if entry[1].candidate_category not in terminal_ai_categories]
    weak = [entry for entry in ranked if entry[1].candidate_type == "weak_reference"]
    # A partner/integration reference may fill spare capacity, but never displace
    # a concrete product candidate merely to add a different dimension.
    for pool in (preferred, other_strong, weak):
        for prefer_new_dimension in (True, False):
            for candidate in pool:
                if candidate in selected:
                    continue
                dimensions = set(candidate[1].shared_dimensions)
                if prefer_new_dimension and dimensions <= covered:
                    continue
                selected.append(candidate)
                covered.update(dimensions)
                if len(selected) >= limit:
                    return selected
    return selected
