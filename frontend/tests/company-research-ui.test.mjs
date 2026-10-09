import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

const panel = await readFile(new URL("../components/applications/CompanyResearchPanel.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../components/applications/ApplicationDetailClient.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../lib/api.ts", import.meta.url), "utf8");
const zh = JSON.parse(await readFile(new URL("../messages/zh.json", import.meta.url), "utf8"));
const en = JSON.parse(await readFile(new URL("../messages/en.json", import.meta.url), "utf8"));

test("application detail exposes company research and calls the application endpoint", () => {
  assert.match(detail, /copy\.companyResearch/);
  assert.match(detail, /setResearchRequest/);
  assert.match(panel, /\/api\/v1\/applications\/\$\{applicationId\}\/company-research/);
  assert.match(panel, /"POST"/);
});

test("company profile freshness and manual regeneration are explicit", () => {
  assert.match(panel, /regenerate_company_profile=true/);
  assert.match(panel, /company_profile_generated_at/);
  assert.match(panel, /company_profile_is_stale/);
  assert.equal(zh.companyResearch.sections.recentSignals, "当前值得关注");
  assert.equal(en.companyResearch.sections.recentSignals, "What to Watch");
  assert.equal(zh.companyResearch.regenerateProfile, "重新生成公司资料");
  assert.match(zh.companyResearch.profileDisclaimer, /模型已有知识并存在滞后/);
});

test("research panel has loading, generated, unavailable, and failure states", () => {
  assert.match(panel, /role="status"/);
  assert.match(panel, /generation_status === "generated"/);
  assert.match(panel, /generation_status === "partial"/);
  assert.match(panel, /partialMessage/);
  assert.match(panel, /generation_status === "unavailable"/);
  assert.match(panel, /generation_status === "failed"/);
  assert.match(panel, /generation_status === "invalid_output"/);
  assert.match(panel, /sectionUnavailable/);
});

test("research brief distinguishes inference and maps evidence to user-facing sources", () => {
  assert.match(panel, /claimType === "inference"/);
  assert.match(panel, /aiAnalysis/);
  assert.match(panel, /buildSourceMap/);
  assert.match(panel, /evidence\.evidence_id/);
  assert.match(panel, /fetchedById\.get\(evidence\.source_id\)/);
  assert.match(panel, /target="_blank"/);
  assert.match(panel, /sourceTypes\.\$\{source\.sourceType\}/);
  assert.doesNotMatch(panel, /extracted_text\}/);
});

test("company research stays within the knowledge boundary", () => {
  assert.doesNotMatch(panel, /copyWhyAnswer/);
  assert.doesNotMatch(panel, /likely_questions\.map/);
  assert.doesNotMatch(panel, /reverse_questions\.items\.map/);
  assert.match(panel, /role_relevant_products_and_scenarios/);
  assert.match(panel, /things_to_understand\.map/);
});

test("company knowledge shows sources only for sourced fields", () => {
  assert.match(panel, /company_knowledge_source_ids/);
  assert.match(panel, /company_knowledge_sources/);
  assert.match(panel, /if \(!sources\.length\) return <AiKnowledgeNotice/);
  assert.match(panel, /t\("viewSources"\)/);
});

test("the final page renders only the six company knowledge sections", () => {
  for (const key of ["companyPositioning", "coreBusiness", "keyBrandsProducts", "customerMarket", "roleRelevantProducts", "comparableProducts"]) assert.match(panel, new RegExp(`sections\\.${key}`));
  assert.doesNotMatch(panel, /recent_signals\.items/);
  assert.doesNotMatch(panel, /role_decoder\.items/);
  assert.doesNotMatch(panel, /what_to_watch/);
});

test("frontend API defines the structured research response instead of rendering raw JSON", () => {
  assert.match(api, /export type CompanyResearchOutput/);
  assert.match(api, /generation_status: ResearchGenerationStatus/);
  assert.doesNotMatch(panel, /JSON\.stringify\(result/);
});

test("role decoder categories always resolve to user-facing translations", () => {
  const expected = {
    role_goal: ["岗位目标", "Role goal"],
    core_responsibilities: ["核心职责", "Core responsibilities"],
    business_scenarios: ["业务场景", "Business scenarios"],
    key_capabilities: ["关键能力", "Key capabilities"],
    why_role_exists: ["为什么需要这个岗位", "Why this role exists"],
  };
  for (const [key, labels] of Object.entries(expected)) {
    assert.equal(zh.companyResearch.categories[key], labels[0]);
    assert.equal(en.companyResearch.categories[key], labels[1]);
    assert.doesNotMatch(labels[0], /companyResearch\.categories/i);
  }
});

test("comparable products use the final interview-knowledge shape", () => {
  assert.match(api, /comparison_dimensions: string\[\]/);
  assert.match(panel, /company_knowledge\.comparable_products/);
  assert.match(panel, /item\.comparison_dimensions/);
  assert.match(panel, /item\.why_relevant/);
  assert.equal(zh.companyResearch.sections.competitiveContext, "同类产品与竞品参考");
  assert.equal(en.companyResearch.sections.competitiveContext, "Comparable Products & Competitor References");
  assert.equal(zh.companyResearch.contextTypes.direct_competitor, "竞品参考");
  assert.equal(zh.companyResearch.contextTypes.comparable_reference, "同类产品");
  assert.equal(en.companyResearch.contextTypes.direct_competitor, "Competitor reference");
  assert.equal(en.companyResearch.contextTypes.comparable_reference, "Comparable product");
  assert.doesNotMatch(panel, /竞争背景/);
  assert.doesNotMatch(JSON.stringify(zh.companyResearch), /竞争背景/);
  assert.match(panel, /safeResearchTranslation/);
  assert.equal(zh.companyResearch.comparisonDimensions, "可比较维度");
});

test("grounded synthesis is represented explicitly", () => {
  assert.match(api, /"grounded_synthesis"/);
  assert.match(panel, /claimType === "grounded_synthesis"/);
  assert.equal(zh.companyResearch.groundedSynthesis, "AI 归纳");
  assert.equal(en.companyResearch.groundedSynthesis, "AI synthesis");
  assert.equal(zh.companyResearch.groundedSynthesisNote, "基于多个公开来源综合整理");
  for (const leaked of [
    "companyResearch.groundedSynthesis",
    "companyResearch.contextTypes.comparable_reference",
    "companyResearch.comparisonDimension",
    "companyResearch.referenceDoes",
    "companyResearch.targetEmphasis",
    "companyResearch.interviewTakeaway",
  ]) assert.notEqual(zh.companyResearch.groundedSynthesis, leaked);
});

test("research source labels distinguish cloud platforms and media types", () => {
  assert.match(panel, /classifyResearchSource/);
  assert.match(panel, /cloud\.tencent\.com/);
  assert.match(panel, /tencentcloud\.com/);
  assert.equal(zh.companyResearch.sourceTypes.cloud_platform, "技术平台");
  assert.equal(en.companyResearch.sourceTypes.cloud_platform, "Technology platform");
  assert.equal(zh.companyResearch.sourceTypes.financial_media, "财经媒体");
  assert.equal(zh.companyResearch.sourceTypes.technology_media, "技术媒体");
  assert.doesNotMatch(panel, /sourceType:\s*fetched\.source_type/);
});

test("GPT-only knowledge is labelled and never renders a fake source button", () => {
  assert.match(panel, /interviewReference/);
  assert.match(panel, /gptOnlyNotice/);
  assert.match(panel, /function SourceDisclosure/);
  assert.match(panel, /if \(!sources\.length\) return null/);
  assert.doesNotMatch(panel, /<SourceDisclosure[^>]*company_knowledge/);
  assert.equal(zh.companyResearch.interviewReference, "AI 面试参考");
  assert.equal(en.companyResearch.interviewReference, "AI interview reference");
});

test("reference labels remain honest and localized", () => {
  assert.match(panel, /referenceTypes\.\$\{item\.reference_type\}/);
  assert.equal(zh.companyResearch.referenceTypes.competitor_reference, "竞品参考");
  assert.equal(zh.companyResearch.referenceTypes.comparable_product, "同类产品");
});

test("no raw company research translation key is user-visible", () => {
  assert.match(panel, /safeLabel/);
  assert.doesNotMatch(JSON.stringify(zh.companyResearch), /companyResearch\.|COMPANYRESEARCH\./);
});
