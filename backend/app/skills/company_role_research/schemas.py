from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


SourceType = Literal[
    "user_provided",
    "official",
    "external",
    "campus",
    "community",
    "ai_inference",
]
WebSourceType = Literal["official", "external", "campus", "community"]
GroundingSourceType = Literal["user_provided", "official", "external", "campus", "community", "ai_inference"]
SectionStatus = Literal["available", "unavailable"]
FetchStatus = Literal["success", "unavailable", "skipped", "failed"]
ClaimType = Literal["fact", "inference", "grounded_synthesis"]
GenerationStatus = Literal["generated", "partial", "unavailable", "failed", "invalid_output"]
EvidenceType = Literal[
    "company",
    "role",
    "recent_signal",
    "competitive",
    "campus_recruitment",
    "interview_experience",
]
EVIDENCE_TYPES_BY_SOURCE: dict[GroundingSourceType, tuple[EvidenceType, ...]] = {
    "user_provided": ("role",),
    "official": ("company", "role", "recent_signal", "competitive", "campus_recruitment"),
    "external": ("company", "recent_signal", "competitive"),
    "campus": ("campus_recruitment", "role"),
    "community": ("interview_experience",),
    "ai_inference": ("company",),
}


class CompanyRoleResearchInput(BaseModel):
    application_id: UUID
    company_name: str = Field(min_length=1)
    job_title: str | None = None
    saved_jd: str | None = None


class SourceMetadata(BaseModel):
    source_type: SourceType
    title: str = Field(min_length=1)
    url: str | None = None
    snippet: str | None = None
    published_at: str | None = None

    @model_validator(mode="after")
    def external_sources_require_urls(self) -> "SourceMetadata":
        if self.source_type in {"official", "external", "campus", "community"} and not self.url:
            raise ValueError("web-discovered sources require a URL")
        return self


class WebSearchSource(BaseModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    snippet: str = ""
    published_at: str | None = None
    source_type: WebSourceType


class FetchedSource(BaseModel):
    source_id: str
    title: str
    url: str
    source_type: WebSourceType
    published_at: str | None = None
    content_type: str | None = None
    extracted_text: str = ""
    fetch_status: FetchStatus
    error: str | None = None


class Evidence(BaseModel):
    evidence_id: str
    source_id: str
    source_type: GroundingSourceType
    evidence_type: EvidenceType
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def source_type_allows_evidence_type(self) -> "Evidence":
        if self.evidence_type not in EVIDENCE_TYPES_BY_SOURCE[self.source_type]:
            raise ValueError(f"{self.source_type} cannot support {self.evidence_type} evidence")
        return self


class ResearchSection(BaseModel):
    status: SectionStatus
    items: list[str] = Field(default_factory=list)
    source_indexes: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def unavailable_sections_are_empty(self) -> "ResearchSection":
        if self.status == "unavailable" and (self.items or self.source_indexes):
            raise ValueError("unavailable sections cannot contain generated content")
        if self.status == "available" and not self.items:
            raise ValueError("available sections require content")
        return self


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GroundedItem(StrictModel):
    text: str = Field(min_length=1, max_length=1_500)
    claim_type: ClaimType
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class CompanyMapItem(GroundedItem):
    category: Literal[
        "company_positioning",
        "core_business",
        "customers",
        "current_focus",
        "financial_operating_context",
    ]


class CompanyMapSection(StrictModel):
    status: SectionStatus
    items: list[CompanyMapItem] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def status_matches_items(self) -> "CompanyMapSection":
        _validate_section_status(self.status, self.items)
        priorities = {
            "company_positioning": 0,
            "core_business": 1,
            "customers": 2,
            "current_focus": 3,
            "financial_operating_context": 4,
        }
        item_priorities = [priorities[item.category] for item in self.items]
        if item_priorities != sorted(item_priorities):
            raise ValueError("company map items must follow the candidate-first priority order")
        if len(set(item.category for item in self.items)) != len(self.items):
            raise ValueError("company map categories cannot be repeated")
        if self.status == "available" and self.items[0].category != "company_positioning":
            raise ValueError("company map must begin with company positioning")
        financial_indexes = [index for index, item in enumerate(self.items) if item.category == "financial_operating_context"]
        if financial_indexes and financial_indexes[0] < 3:
            raise ValueError("financial context cannot appear in the first three company map items")
        return self


class RoleDecoderItem(GroundedItem):
    category: Literal[
        "role_goal",
        "core_responsibilities",
        "business_scenarios",
        "key_capabilities",
        "why_role_exists",
    ]

    @model_validator(mode="after")
    def enforce_role_decoder_contract(self) -> "RoleDecoderItem":
        expected_claim_type = "fact" if self.category in {"core_responsibilities", "key_capabilities"} else "inference"
        if self.claim_type != expected_claim_type:
            raise ValueError(f"{self.category} must be {expected_claim_type}")
        if re.search(r"我很适合|候选人适合|你的经历|你的简历|我的经历|我的简历|candidate fit", self.text, re.I):
            raise ValueError("role decoder cannot contain candidate-fit assessment")
        normalized = re.sub(r"[，。、；：\s]", "", self.text)
        if self.category == "business_scenarios" and normalized in {
            "AI场景", "企业业务", "多种业务需求", "多种业务场景", "广泛业务场景",
        }:
            raise ValueError("business scenarios must name concrete supported scenarios")
        if self.category == "key_capabilities" and normalized in {
            "沟通能力强", "学习能力强", "沟通能力强学习能力强", "沟通能力和学习能力强", "良好的沟通能力", "较强的学习能力",
        }:
            raise ValueError("key capabilities cannot consist only of generic soft skills")
        return self


class RoleDecoderSection(StrictModel):
    status: SectionStatus
    items: list[RoleDecoderItem] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def status_matches_items(self) -> "RoleDecoderSection":
        _validate_section_status(self.status, self.items)
        priorities = {
            "role_goal": 0,
            "core_responsibilities": 1,
            "business_scenarios": 2,
            "key_capabilities": 3,
            "why_role_exists": 4,
        }
        item_priorities = [priorities[item.category] for item in self.items]
        if item_priorities != sorted(item_priorities):
            raise ValueError("role decoder items must follow the fixed candidate-first order")
        if len(set(item.category for item in self.items)) != len(self.items):
            raise ValueError("role decoder categories cannot be repeated")
        if self.status == "available" and self.items[0].category != "role_goal":
            raise ValueError("role decoder must begin with role goal")
        return self


class RecentSignalItem(StrictModel):
    title: str = Field(min_length=1, max_length=1_500, validation_alias=AliasChoices("title", "signal"))
    date: str | None = Field(default=None, max_length=40)
    why_it_matters_for_interview: str = Field(min_length=1, max_length=1_000)
    role_relevance: Literal["high", "medium", "low"]
    claim_type: Literal["fact"] = "fact"
    evidence_ids: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def interview_relevance_is_specific(self) -> "RecentSignalItem":
        generic_explanations = {
            "需要关注公司发展", "需要理解资源投入", "需要关注行业趋势",
            "有助于了解公司发展", "有助于了解行业趋势", "值得候选人关注",
        }
        normalized = re.sub(r"[，。、；：\s]", "", self.why_it_matters_for_interview)
        if normalized in generic_explanations:
            raise ValueError("recent signal interview relevance must explain a concrete role or interview impact")
        concrete_anchors = (
            "岗位", "面试", "回答", "产品", "业务线", "团队", "职责", "方案",
            "场景", "用户", "工作流", "评估", "能力", "优先级", "商业化", "成本", "规模化",
        )
        if not any(anchor in self.why_it_matters_for_interview for anchor in concrete_anchors):
            raise ValueError("recent signal interview relevance lacks a concrete role or interview connection")
        return self


class RecentSignalsSection(StrictModel):
    status: SectionStatus
    items: list[RecentSignalItem] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def status_matches_items(self) -> "RecentSignalsSection":
        _validate_section_status(self.status, self.items)
        if self.status == "available" and any(item.role_relevance == "low" for item in self.items):
            raise ValueError("low-relevance signals cannot enter the main recent signals list")
        return self


class CompetitiveContextItem(StrictModel):
    context_type: Literal["direct_competitor", "comparable_reference"]
    competitor: str = Field(min_length=1, max_length=300)
    comparison_dimension: str = Field(min_length=1, max_length=500)
    observed_difference: str = Field(min_length=1, max_length=1_500)
    interview_relevance: str = Field(min_length=1, max_length=1_000)
    what_reference_does: str | None = Field(default=None, min_length=1, max_length=1_500)
    what_target_role_emphasizes: str | None = Field(default=None, min_length=1, max_length=600)
    interview_takeaway: str | None = Field(default=None, min_length=1, max_length=1_000)
    claim_type: Literal["fact", "grounded_synthesis"] = "fact"
    evidence_ids: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def reject_generic_competition_language(self) -> "CompetitiveContextItem":
        generic_competitors = {
            "多个头部厂商", "多个顶级厂商", "头部厂商", "头部互联网公司", "行业玩家",
            "行业领先企业", "主要厂商", "主要竞争对手", "其他厂商", "竞争对手",
            "Claw", "AI Agent", "AI Agents", "Agent", "Agents", "Now", "Today",
        }
        generic_dimensions = {"综合实力", "产品能力", "市场竞争", "AI能力", "AI 能力", "竞争格局", "技术能力"}
        vague_differences = (
            "多个头部厂商竞争激烈", "市场竞争激烈", "竞争十分激烈", "行业竞争激烈",
            "各有优势", "差异化竞争优势", "形成差异化", "技术路线不同", "更有生态优势",
        )
        generic_relevance = {
            "理解竞争格局有助于产品设计", "有助于把握差异化特色", "有助于理解行业趋势",
            "帮助理解竞争格局", "有助于产品设计", "需要关注竞争格局",
        }
        normalized_relevance = re.sub(r"[，。、；：\s]", "", self.interview_relevance)
        if self.competitor.strip() in generic_competitors or re.search(
            r"^(?:同级|同等|同类|其他|主要|若干|多个)",
            self.competitor.strip(),
        ) or re.search(
            r"(?:attention|architecture|capability|capabilities|架构|解码|算法|能力)$",
            self.competitor.strip(),
            re.I,
        ) or self.competitor.strip().endswith("-"):
            raise ValueError("competitive context requires a specifically named company, product, or platform")
        if self.comparison_dimension.strip() in generic_dimensions:
            raise ValueError("competitive context requires a concrete comparison dimension")
        if any(phrase in self.observed_difference for phrase in vague_differences):
            raise ValueError("competitive context requires a concrete evidence-supported difference")
        if normalized_relevance in generic_relevance:
            raise ValueError("competitive context requires a concrete interview impact")
        relevance_anchors = (
            "岗位", "面试", "回答", "产品", "方案", "设计", "工作流", "技能", "Tool",
            "工具", "知识", "协同", "设备", "模型", "开发者", "商业化", "ToB", "ToC", "场景",
        )
        if not any(anchor in self.interview_relevance for anchor in relevance_anchors):
            raise ValueError("competitive context interview relevance lacks a role or product connection")
        if self.context_type == "comparable_reference":
            if not self.what_reference_does:
                raise ValueError("comparable reference requires an external capability description")
            if not self.what_target_role_emphasizes:
                raise ValueError("comparable reference requires a target-side emphasis")
            if not self.interview_takeaway:
                raise ValueError("comparable reference requires a concrete interview takeaway")
            if self.claim_type != "grounded_synthesis":
                raise ValueError("comparable reference must be grounded synthesis")
            vague_takeaways = {"有助于了解行业", "有助于了解竞争", "值得关注", "帮助理解行业"}
            if re.sub(r"[，。、；：\s]", "", self.interview_takeaway) in vague_takeaways:
                raise ValueError("comparable reference requires a concrete interview takeaway")
        superiority = r"(?:小米|目标公司|本公司).{0,8}(?:更强|更先进|领先|更有优势)|(?:对方|参考产品).{0,8}(?:更弱|落后|只做软件)"
        comparison_text = " ".join(filter(None, (
            self.observed_difference, self.what_reference_does,
            self.what_target_role_emphasizes, self.interview_takeaway,
        )))
        if re.search(superiority, comparison_text, re.I):
            raise ValueError("competitive comparison contains unsupported superiority claim")
        return self


class CompetitiveContextSection(StrictModel):
    status: SectionStatus
    items: list[CompetitiveContextItem] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def status_matches_items(self) -> "CompetitiveContextSection":
        _validate_section_status(self.status, self.items)
        return self


class InterviewFocusItem(StrictModel):
    focus_area: str = Field(min_length=1, max_length=500)
    why_likely: str = Field(min_length=1, max_length=1_000)
    likely_questions: list[str] = Field(min_length=2, max_length=4)
    preparation_focus: str = Field(min_length=1, max_length=1_000)
    confidence: Literal["high", "medium", "low"]
    claim_type: Literal["inference"] = "inference"
    evidence_ids: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def enforce_interview_preparation_contract(self) -> "InterviewFocusItem":
        generic_focus_areas = {"产品能力", "AI能力", "AI 能力", "综合素质", "沟通能力", "学习能力"}
        generic_reasons = {"这是岗位主要职责", "这项能力很重要", "面试官可能会关注", "该能力非常重要"}
        generic_preparation = {"多了解公司", "多准备项目", "多学习AI", "多学习 AI", "提前熟悉岗位", "提前准备相关知识"}
        normalize = lambda text: re.sub(r"[，。、；：\s]", "", text)
        if self.focus_area.strip() in generic_focus_areas:
            raise ValueError("interview focus requires a specific, preparable topic")
        if normalize(self.why_likely) in generic_reasons:
            raise ValueError("why_likely must connect the focus to specific role evidence")
        if normalize(self.preparation_focus) in generic_preparation:
            raise ValueError("preparation_focus must prescribe concrete preparation")
        if len(set(normalize(question) for question in self.likely_questions)) != len(self.likely_questions):
            raise ValueError("likely questions cannot be duplicated")
        if any(not question.strip().endswith(("？", "?")) for question in self.likely_questions):
            raise ValueError("likely questions must be phrased as questions")
        combined = f"{self.focus_area} {self.why_likely} {self.preparation_focus}"
        if re.search(r"我的简历|我的经历|过往经历|我很适合|你很适合|候选人适合|candidate fit", combined, re.I):
            raise ValueError("interview focus cannot contain candidate-fit assessment")
        return self


class InterviewFocusSection(StrictModel):
    status: SectionStatus
    items: list[InterviewFocusItem] = Field(default_factory=list, min_length=0, max_length=5)

    @model_validator(mode="after")
    def status_matches_items(self) -> "InterviewFocusSection":
        _validate_section_status(self.status, self.items, available_minimum=2)
        if self.status == "available" and any(item.confidence == "low" for item in self.items):
            raise ValueError("low-confidence interview focus cannot enter the main list")
        return self


class WhyCompanyRoleItem(StrictModel):
    text: str = Field(min_length=120, max_length=220)
    claim_type: Literal["inference"] = "inference"
    evidence_ids: list[str] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def reject_corporate_cliches(self) -> "WhyCompanyRoleItem":
        banned = (
            "深厚积累", "创新活力", "前瞻战略", "技术实力雄厚", "行业领先", "引领创新",
            "赋能", "深度融合", "助力公司", "全流程管理", "实现成长和贡献", "技术与业务双重领先",
        )
        if any(term in self.text for term in banned):
            raise ValueError("why-company answer contains corporate cliches")
        company_markers = ("我选择", "我关注", "我比较看重", "选择这家公司", "这家公司吸引")
        role_markers = ("这个岗位吸引", "岗位吸引", "选择这个岗位", "这个岗位", "岗位本身")
        motivation_markers = ("对我来说", "我希望继续", "我想继续", "很有吸引力", "我愿意继续")
        if not any(marker in self.text for marker in company_markers):
            raise ValueError("why-company answer must include a clear company reason")
        if not any(marker in self.text for marker in role_markers):
            raise ValueError("why-company answer must include a clear role reason")
        if not any(marker in self.text for marker in motivation_markers):
            raise ValueError("why-company answer must include personal direction motivation without candidate fit")
        financial_terms = ("营收", "利润", "毛利率", "同比增长", "同比下降")
        product_context_terms = ("业务", "产品", "用户", "客户", "场景", "技术", "AI", "服务", "能力")
        if any(term in self.text for term in financial_terms) and not any(term in self.text for term in product_context_terms):
            raise ValueError("company reason cannot rely only on financial data")
        return self


class WhyCompanyRoleSection(StrictModel):
    status: SectionStatus
    items: list[WhyCompanyRoleItem] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def status_matches_items(self) -> "WhyCompanyRoleSection":
        _validate_section_status(self.status, self.items)
        return self


class ReverseQuestionItem(StrictModel):
    question: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=800)
    claim_type: Literal["inference"] = "inference"
    evidence_ids: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def keep_question_junior_friendly(self) -> "ReverseQuestionItem":
        overly_senior = re.compile(r"EBITDA|资本开支|组织重构|战略协同|市场份额目标|商业化效率", re.I)
        if overly_senior.search(self.question):
            raise ValueError("reverse question is not appropriate for a junior candidate")
        methodology_patterns = (
            r"AI\s*Agent\s*产品如何与.*(?:算法|工程|研发).*协作",
            r"如何做跨团队协作", r"如何定义.*MVP", r"如何评估.*(?:Agent|AI|效果)",
            r"什么时候.*RAG.*Tool\s*Calling", r"如何设计.*(?:Agent|任务编排|技能体系|平台)",
            r"如何处理.*模型.*不稳定", r"如何解决.*模型幻觉", r"如何控制.*(?:成本|延迟)",
        )
        if any(re.search(pattern, self.question, re.I) for pattern in methodology_patterns):
            raise ValueError("candidate methodology questions belong in likely interview focus")
        expert_diligence = re.compile(r"orchestration architecture|推理成本.*长期模型战略|长期模型战略.*trade-?off|架构.*核心瓶颈", re.I)
        if expert_diligence.search(self.question):
            raise ValueError("reverse question is overly technical diligence for a junior candidate")
        if not self.question.strip().endswith(("？", "?")):
            raise ValueError("reverse question must be phrased as a question")
        generic_rationales = {"有助于面试准备", "有助于了解公司", "有助于理解岗位", "帮助了解岗位", "帮助面试准备"}
        normalized_rationale = re.sub(r"[，。、；：\s]", "", self.rationale)
        if normalized_rationale in generic_rationales:
            raise ValueError("reverse question rationale must explain the specific information gained")
        rationale_anchors = (
            "入职", "工作内容", "新人", "预期", "团队", "重点", "分工", "协作", "标准",
            "目标", "指标", "挑战", "业务", "产品", "项目", "场景", "职责",
        )
        if not any(anchor in self.rationale for anchor in rationale_anchors):
            raise ValueError("reverse question rationale lacks a concrete learning objective")
        if re.search(r"我的简历|我的经历|我很适合|候选人适合|candidate fit", f"{self.question} {self.rationale}", re.I):
            raise ValueError("reverse questions cannot contain candidate-fit assessment")
        return self


class ReverseQuestionsSection(StrictModel):
    status: SectionStatus
    items: list[ReverseQuestionItem] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def status_matches_items(self) -> "ReverseQuestionsSection":
        _validate_section_status(self.status, self.items, available_minimum=2)
        normalized = [re.sub(r"[，。、；：？！?\s]", "", item.question) for item in self.items]
        if len(set(normalized)) != len(normalized):
            raise ValueError("reverse questions cannot be duplicated")

        def question_theme(question: str) -> str | None:
            themes = {
                "onboarding": ("前三个月", "前3个月", "入职初期", "新人", "刚加入", "刚开始", "先负责", "从哪类项目"),
                "team_priority": ("团队目前", "团队当前", "最优先", "重点推进", "最希望优先"),
                "collaboration": ("怎么分工", "如何分工", "协作方式", "通常怎么协作", "通常如何协作"),
                "success": ("做得好不好", "成功标准", "工作效果", "结果指标", "目标或预期"),
                "challenge": ("主要挑战", "最大挑战", "最大的业务挑战", "最需要解决的问题"),
            }
            return next((theme for theme, markers in themes.items() if any(marker in question for marker in markers)), None)

        recognized_themes = [theme for item in self.items if (theme := question_theme(item.question))]
        if len(set(recognized_themes)) != len(recognized_themes):
            raise ValueError("reverse questions cannot repeat the same information need")
        return self


def _validate_section_status(status: SectionStatus, items: list, available_minimum: int = 1) -> None:
    if status == "unavailable" and items:
        raise ValueError("unavailable sections cannot contain generated content")
    if status == "available" and len(items) < available_minimum:
        raise ValueError(f"available section requires at least {available_minimum} item(s)")


class GroundedResearchGeneration(StrictModel):
    company_map: CompanyMapSection
    role_decoder: RoleDecoderSection
    recent_signals: RecentSignalsSection
    competitive_context: CompetitiveContextSection
    likely_interview_focus: InterviewFocusSection
    why_company_why_role_60s: WhyCompanyRoleSection
    reverse_questions: ReverseQuestionsSection


class RecentInterviewReferenceItem(StrictModel):
    watch_topic: str
    why_relevant: str
    what_to_learn: list[str] = Field(default_factory=list, min_length=2, max_length=5)


class RoleRelevantProductItem(StrictModel):
    name: str
    type: Literal["product", "platform", "brand", "ecosystem", "capability", "business"]
    relevance_to_role: str
    key_scenarios: list[str] = Field(default_factory=list, min_length=1, max_length=5)
    things_to_understand: list[str] = Field(default_factory=list, min_length=2, max_length=5)


class CompetitiveInterviewReferenceItem(StrictModel):
    entity_name: str
    reference_type: Literal["competitor_reference", "comparable_product"]
    shared_dimension: str
    why_relevant: str
    interview_angle: str


class CompanyKnowledgeComparableItem(StrictModel):
    entity_name: str
    reference_type: Literal["competitor_reference", "comparable_product"]
    why_relevant: str
    comparison_dimensions: list[str] = Field(min_length=1, max_length=5)


class CompanyKnowledge(StrictModel):
    company_positioning: str | None = None
    core_business: list[str] = Field(default_factory=list, max_length=8)
    key_brands_and_products: list[str] = Field(default_factory=list, max_length=12)
    customer_and_market: list[str] = Field(default_factory=list, max_length=8)
    role_relevant_products_and_scenarios: list[RoleRelevantProductItem] = Field(default_factory=list, max_length=6)
    comparable_products: list[CompanyKnowledgeComparableItem] = Field(default_factory=list, max_length=3)


class CompanyKnowledgeSource(StrictModel):
    source_id: str
    title: str
    url: str
    source_type: WebSourceType
    published_at: str | None = None
    category: str | None = None


class WhyInterviewReference(StrictModel):
    company_reason: str
    role_reason: str
    personal_motivation_prompt: str
    sample_answer: str


class InterviewReferenceFallbacks(StrictModel):
    recent_signals_status: Literal["interview_reference", "unavailable"] = "unavailable"
    recent_signals: list[RecentInterviewReferenceItem] = Field(default_factory=list, max_length=3)
    competitive_context_status: Literal["interview_reference", "unavailable"] = "unavailable"
    competitive_context: list[CompetitiveInterviewReferenceItem] = Field(default_factory=list, max_length=3)
    why_company_role_status: Literal["interview_reference", "unavailable"] = "unavailable"
    why_company_role: WhyInterviewReference | None = None


class CompanyRoleResearchOutput(BaseModel):
    application_id: UUID
    company_name: str
    job_title: str | None
    company_map: CompanyMapSection
    role_decoder: RoleDecoderSection
    recent_signals: RecentSignalsSection
    competitive_context: CompetitiveContextSection
    likely_interview_focus: InterviewFocusSection
    why_company_why_role_60s: WhyCompanyRoleSection
    reverse_questions: ReverseQuestionsSection
    sources: list[SourceMetadata]
    fetched_sources: list[FetchedSource] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    interview_references: InterviewReferenceFallbacks = Field(default_factory=InterviewReferenceFallbacks)
    company_knowledge: CompanyKnowledge = Field(default_factory=CompanyKnowledge)
    company_knowledge_source_ids: dict[str, list[str]] = Field(default_factory=dict)
    company_knowledge_sources: list[CompanyKnowledgeSource] = Field(default_factory=list)
    generation_status: GenerationStatus = "unavailable"
    company_profile_generated_at: str | None = None
    company_profile_refreshed_at: str | None = None
    company_profile_is_stale: bool = False
    company_profile_cache_hit: bool = False
