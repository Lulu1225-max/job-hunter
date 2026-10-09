"use client";

import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {ExternalLink, RefreshCw, Search, Sparkles} from "lucide-react";
import {useLocale, useTranslations} from "next-intl";
import {
  apiSend,
  type CompanyResearchOutput,
  type ResearchClaimType,
  type ResearchEvidence,
  type ResearchFetchedSource,
  type ResearchSectionStatus,
} from "@/lib/api";

type ResearchSourceDisplayType =
  | "official_company"
  | "official_product"
  | "cloud_platform"
  | "technology_media"
  | "financial_media"
  | "campus"
  | "community"
  | "ai_inference"
  | "user_provided";

type SourceDisplay = {
  sourceId: string;
  title: string;
  sourceType: ResearchSourceDisplayType;
  publishedAt?: string | null;
  url?: string;
};

export function CompanyResearchPanel({applicationId, requestKey = 0}: {applicationId: string; requestKey?: number}) {
  const t = useTranslations("companyResearch");
  const locale = useLocale();
  const safeLabel = (key: string, zh: string, en: string) => safeResearchTranslation(t, key, locale === "zh" ? zh : en);
  const [result, setResult] = useState<CompanyResearchOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [requestFailed, setRequestFailed] = useState(false);
  const handledRequestKey = useRef(0);

  const sourceByEvidenceId = useMemo(() => buildSourceMap(result, t("userProvided")), [result, t]);

  const generateResearch = useCallback(async (regenerateProfile = false) => {
    setLoading(true);
    setRequestFailed(false);
    try {
      const response = await apiSend<CompanyResearchOutput>(
        `/api/v1/applications/${applicationId}/company-research${regenerateProfile ? "?regenerate_company_profile=true" : ""}`,
        "POST",
      );
      setResult(response);
    } catch {
      setResult(null);
      setRequestFailed(true);
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    if (requestKey > handledRequestKey.current) {
      handledRequestKey.current = requestKey;
      void generateResearch(false);
    }
  }, [generateResearch, requestKey]);

  const overallFailure = requestFailed || result?.generation_status === "failed" || result?.generation_status === "invalid_output";
  const overallUnavailable = result?.generation_status === "unavailable";
  const showReport = result?.generation_status === "generated" || result?.generation_status === "partial";

  return (
    <section id="company-research" className="surface-card overflow-hidden" aria-labelledby="company-research-title">
      <div className="flex flex-col gap-4 border-b border-line bg-[hsl(var(--primary-soft)/0.45)] p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-brand">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            <p className="text-xs font-semibold uppercase tracking-[0.14em]">{t("eyebrow")}</p>
          </div>
          <h2 id="company-research-title" className="mt-2 text-xl font-semibold text-ink">{t("title")}</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">{t("description")}</p>
        </div>
        <button type="button" onClick={() => void generateResearch(false)} disabled={loading} className="btn-primary shrink-0 gap-2">
          {result || overallFailure ? <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> : <Search className="h-4 w-4" />}
          {loading ? t("researching") : result || overallFailure ? t("retry") : t("start")}
        </button>
      </div>

      {loading && <ResearchLoading label={t("loadingMessage")} />}

      {!loading && !result && !overallFailure && (
        <div className="p-5 text-sm leading-6 text-muted">{t("idleMessage")}</div>
      )}

      {!loading && overallFailure && (
        <div role="alert" className="m-5 rounded-md border border-[hsl(var(--danger)/0.24)] bg-[hsl(var(--danger-soft))] p-4">
          <p className="font-medium text-[hsl(var(--danger))]">{t("failedTitle")}</p>
          <p className="mt-1 text-sm text-muted">{t("failedMessage")}</p>
        </div>
      )}

      {!loading && overallUnavailable && (
        <div className="m-5 rounded-md border border-line bg-surface-muted p-4 text-sm text-muted">
          {t("overallUnavailable")}
        </div>
      )}

      {!loading && result?.generation_status === "partial" && (
        <div className="mx-5 mt-5 rounded-md border border-line bg-surface-muted px-4 py-3 text-sm text-muted md:mx-6">
          {t("partialMessage")}
        </div>
      )}

      {!loading && result && (
        <div className="mx-5 mt-5 flex flex-col gap-3 rounded-md border border-line bg-surface-muted px-4 py-3 text-sm text-muted md:mx-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p>{t("profileDisclaimer")}</p>
            {result.company_profile_generated_at && (
              <p className="mt-1 text-xs">{t("profileGeneratedAt")}：{new Intl.DateTimeFormat(locale, {dateStyle: "medium"}).format(new Date(result.company_profile_generated_at))}</p>
            )}
            {result.company_profile_is_stale && <p className="mt-1 font-medium text-[hsl(var(--warning))]">{t("profileStale")}</p>}
          </div>
          <button type="button" onClick={() => void generateResearch(true)} disabled={loading} className="btn-secondary shrink-0 gap-2">
            <RefreshCw className="h-4 w-4" />{t("regenerateProfile")}
          </button>
        </div>
      )}

      {!loading && showReport && (
        <div className="space-y-5 p-5 md:p-6">
          <ResearchSection title={`1. ${safeLabel("sections.companyPositioning", "公司定位", "Company Positioning")}`} status={result.company_knowledge.company_positioning ? "available" : "unavailable"} unavailable={t("sectionUnavailable")}>
            <KnowledgeProvenance result={result} section="company_positioning" />
            {result.company_knowledge.company_positioning && <p className="rounded-md border border-line/80 bg-[hsl(var(--surface))] p-4 leading-7 text-ink">{result.company_knowledge.company_positioning}</p>}
          </ResearchSection>

          <ResearchSection title={`2. ${safeLabel("sections.coreBusiness", "主营业务", "Core Business")}`} status={result.company_knowledge.core_business.length ? "available" : "unavailable"} unavailable={t("sectionUnavailable")}>
            <KnowledgeProvenance result={result} section="core_business" />
            <KnowledgePills values={result.company_knowledge.core_business} />
          </ResearchSection>

          <ResearchSection title={`3. ${safeLabel("sections.keyBrandsProducts", "核心品牌与产品", "Key Brands & Products")}`} status={result.company_knowledge.key_brands_and_products.length ? "available" : "unavailable"} unavailable={t("sectionUnavailable")}>
            <KnowledgeProvenance result={result} section="key_brands_and_products" />
            <KnowledgePills values={result.company_knowledge.key_brands_and_products} />
          </ResearchSection>

          <ResearchSection title={`4. ${safeLabel("sections.customerMarket", "用户与市场", "Customers & Market")}`} status={result.company_knowledge.customer_and_market.length ? "available" : "unavailable"} unavailable={t("sectionUnavailable")}>
            <KnowledgeProvenance result={result} section="customer_and_market" />
            <KnowledgePills values={result.company_knowledge.customer_and_market} />
          </ResearchSection>

          <ResearchSection title={`5. ${safeLabel("sections.roleRelevantProducts", "与岗位最相关的产品与场景", "Role-relevant Products & Scenarios")}`} status={result.company_knowledge.role_relevant_products_and_scenarios.length ? "available" : "unavailable"} unavailable={t("sectionUnavailable")}>
            <AiKnowledgeNotice />
            {result.company_knowledge.role_relevant_products_and_scenarios.map((item) => (
              <article key={item.name} className="rounded-md border border-line/80 bg-[hsl(var(--surface))] p-4">
                <div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-ink">{item.name}</p><span className="rounded-full bg-mintsoft px-2 py-0.5 text-xs font-medium text-emerald-800">{safeLabel(`knowledgeTypes.${item.type}`, item.type === "business" ? "业务" : item.type, item.type)}</span></div>
                <p className="mt-3 text-sm leading-6 text-muted"><span className="font-medium text-ink">{safeLabel("relevanceToRole", "与岗位的关系", "Relevance to the role")}：</span>{item.relevance_to_role}</p>
                <p className="mt-3 text-sm font-medium text-ink">{safeLabel("keyScenarios", "关键场景", "Key scenarios")}</p><ul className="mt-1 space-y-1 text-sm text-muted">{item.key_scenarios.map((value) => <li key={value}>• {value}</li>)}</ul>
                <p className="mt-3 text-sm font-medium text-ink">{safeLabel("thingsToUnderstand", "面试前建议重点了解", "What to understand before the interview")}</p><ul className="mt-1 space-y-1 text-sm text-muted">{item.things_to_understand.map((value) => <li key={value}>• {value}</li>)}</ul>
              </article>
            ))}
          </ResearchSection>

          <ResearchSection title={`6. ${safeLabel("sections.comparableProducts", "同类产品与竞品参考", "Comparable Products & Competitor References")}`} status={result.company_knowledge.comparable_products.length ? "available" : "unavailable"} unavailable={t("sectionUnavailable")}>
            <AiKnowledgeNotice />
            {result.company_knowledge.comparable_products.map((item) => <article key={item.entity_name} className="rounded-md border border-line/80 bg-[hsl(var(--surface))] p-4"><span className="rounded-full bg-mintsoft px-2 py-0.5 text-xs font-medium text-emerald-800">{safeLabel(`referenceTypes.${item.reference_type}`, item.reference_type === "competitor_reference" ? "竞品参考" : "同类产品", item.reference_type === "competitor_reference" ? "Competitor reference" : "Comparable product")}</span><p className="mt-2 font-semibold text-ink">{item.entity_name}</p><p className="mt-3 text-sm leading-6 text-muted"><span className="font-medium text-ink">{safeLabel("whyRelevant", "为什么值得了解", "Why it is worth reviewing")}：</span>{item.why_relevant}</p><p className="mt-3 text-sm font-medium text-ink">{safeLabel("comparisonDimensions", "可比较维度", "Comparison dimensions")}</p><ul className="mt-1 space-y-1 text-sm text-muted">{item.comparison_dimensions.map((value) => <li key={value}>• {value}</li>)}</ul></article>)}
          </ResearchSection>

        </div>
      )}
    </section>
  );
}

function KnowledgePills({values}: {values: string[]}) { return <div className="flex flex-wrap gap-2">{values.map((value) => <span key={value} className="rounded-full bg-surface-muted px-3 py-1.5 text-sm text-ink">{value}</span>)}</div>; }

function AiKnowledgeNotice() { const t = useTranslations("companyResearch"); return <div className="flex flex-wrap items-center gap-2 text-xs text-muted"><span className="rounded-full bg-mintsoft px-2 py-0.5 font-semibold text-emerald-800">{t("interviewReference")}</span><span>{t("gptOnlyNotice")}</span></div>; }

function KnowledgeProvenance({result, section}: {result: CompanyResearchOutput; section: string}) {
  const t = useTranslations("companyResearch");
  const [expanded, setExpanded] = useState(false);
  const ids = result.company_knowledge_source_ids?.[section] ?? [];
  const sources = (result.company_knowledge_sources ?? []).filter((source) => ids.includes(source.source_id));
  if (!sources.length) return <AiKnowledgeNotice />;
  return <div className="text-xs text-muted"><button type="button" className="font-semibold text-brand hover:underline" onClick={() => setExpanded((value) => !value)}>{t("viewSources")}</button>{expanded && <ul className="mt-2 space-y-1">{sources.map((source) => <li key={source.source_id}><a className="inline-flex items-center gap-1 hover:text-brand" href={source.url} target="_blank" rel="noreferrer">{source.title}<ExternalLink className="h-3 w-3" /></a></li>)}</ul>}</div>;
}

function ResearchSection({title, status, unavailable, emphasized = false, children}: {title: string; status: ResearchSectionStatus; unavailable: string; emphasized?: boolean; children: React.ReactNode}) {
  return (
    <section className={`rounded-lg border p-4 md:p-5 ${emphasized ? "border-brand/25 bg-[hsl(var(--primary-soft)/0.28)]" : "border-line bg-white"}`}>
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      {status === "unavailable" ? <p className="mt-3 rounded-md bg-surface-muted px-3 py-2 text-sm text-muted">{unavailable}</p> : <div className="mt-4 space-y-3">{children}</div>}
    </section>
  );
}

function InterviewReferenceNotice({note, children}: {note: string; children: React.ReactNode}) {
  const t = useTranslations("companyResearch");
  return <div className="space-y-3"><div className="rounded-md border border-brand/15 bg-[hsl(var(--primary-soft)/0.22)] px-3 py-2"><span className="inline-flex rounded-full bg-mintsoft px-2 py-0.5 text-xs font-semibold text-emerald-800">{t("interviewReference")}</span><p className="mt-2 text-xs leading-5 text-muted">{note}</p></div>{children}</div>;
}

function BriefItem({claimType, evidenceIds, sourceMap, emphasized = false, children}: {claimType: ResearchClaimType; evidenceIds: string[]; sourceMap: Map<string, SourceDisplay>; emphasized?: boolean; children: React.ReactNode}) {
  const t = useTranslations("companyResearch");
  const locale = useLocale();
  return (
    <article className={`rounded-md border border-line/80 p-4 ${emphasized ? "bg-white" : "bg-[hsl(var(--surface))]"}`}>
      {claimType === "inference" && <span className="mb-3 inline-flex rounded-full bg-mintsoft px-2 py-0.5 text-xs font-semibold text-emerald-800">{t("aiAnalysis")}</span>}
      {claimType === "grounded_synthesis" && <div className="mb-3 flex flex-wrap items-center gap-2"><span className="inline-flex rounded-full bg-mintsoft px-2 py-0.5 text-xs font-semibold text-emerald-800">{safeResearchTranslation(t, "groundedSynthesis", locale === "zh" ? "AI 归纳" : "AI synthesis")}</span><span className="text-xs text-muted">{safeResearchTranslation(t, "groundedSynthesisNote", locale === "zh" ? "基于多个公开来源综合整理" : "Synthesized from multiple public sources")}</span></div>}
      {children}
      <SourceDisclosure evidenceIds={evidenceIds} sourceMap={sourceMap} />
    </article>
  );
}

function safeResearchTranslation(translate: (key: never) => string, key: string, fallback: string): string {
  try {
    const value = translate(key as never);
    return value === key || value.startsWith("companyResearch.") ? fallback : value;
  } catch {
    return fallback;
  }
}

function SourceDisclosure({evidenceIds, sourceMap}: {evidenceIds: string[]; sourceMap: Map<string, SourceDisplay>}) {
  const t = useTranslations("companyResearch");
  const sources = Array.from(new Map(evidenceIds.map((id) => sourceMap.get(id)).filter(Boolean).map((source) => [source!.sourceId, source!])).values());
  if (!sources.length) return null;
  return (
    <details className="mt-4 border-t border-line/70 pt-3">
      <summary className="cursor-pointer text-xs font-semibold text-brand hover:text-brand-hover">{t("viewSources")} · {sources.length}</summary>
      <div className="mt-3 space-y-2">
        {sources.map((source) => (
          <div key={source.sourceId} className="rounded-md bg-surface-muted px-3 py-2 text-xs">
            <div className="flex flex-wrap items-center gap-2"><span className="font-medium text-ink">{source.title}</span><span className="rounded-full border border-line bg-white px-2 py-0.5 text-muted">{t(`sourceTypes.${source.sourceType}`)}</span></div>
            {source.publishedAt && <p className="mt-1 text-muted">{source.publishedAt}</p>}
            {source.url && <a href={source.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 break-all text-brand hover:underline">{t("openSource")}<ExternalLink className="h-3 w-3 shrink-0" /></a>}
          </div>
        ))}
      </div>
    </details>
  );
}

function ResearchLoading({label}: {label: string}) {
  return (
    <div role="status" aria-live="polite" className="space-y-4 p-5 md:p-6">
      <div className="flex items-center gap-2 text-sm font-medium text-brand"><RefreshCw className="h-4 w-4 animate-spin" />{label}</div>
      {[0, 1, 2].map((item) => <div key={item} className="animate-pulse rounded-lg border border-line p-4"><div className="h-4 w-40 rounded bg-surface-muted" /><div className="mt-4 h-3 w-full rounded bg-surface-muted" /><div className="mt-2 h-3 w-4/5 rounded bg-surface-muted" /></div>)}
    </div>
  );
}

function buildSourceMap(result: CompanyResearchOutput | null, userProvidedTitle: string) {
  const map = new Map<string, SourceDisplay>();
  if (!result) return map;
  const fetchedById = new Map<string, ResearchFetchedSource>(result.fetched_sources.map((source) => [source.source_id, source]));
  result.evidence.forEach((evidence: ResearchEvidence) => {
    const fetched = fetchedById.get(evidence.source_id);
    map.set(evidence.evidence_id, fetched ? {
      sourceId: fetched.source_id,
      title: fetched.title,
      sourceType: classifyResearchSource(fetched),
      publishedAt: fetched.published_at,
      url: fetched.url,
    } : {
      sourceId: evidence.source_id,
      title: userProvidedTitle,
      sourceType: classifyUnfetchedSource(evidence.source_type),
    });
  });
  return map;
}

function classifyUnfetchedSource(sourceType: ResearchEvidence["source_type"]): ResearchSourceDisplayType {
  if (sourceType === "user_provided") return "user_provided";
  if (sourceType === "ai_inference") return "ai_inference";
  if (sourceType === "community") return "community";
  if (sourceType === "campus") return "campus";
  if (sourceType === "official") return "official_company";
  return "technology_media";
}

function classifyResearchSource(source: ResearchFetchedSource): ResearchSourceDisplayType {
  const hostname = (() => {
    try {
      return new URL(source.url).hostname.toLowerCase().replace(/^www\./, "");
    } catch {
      return "";
    }
  })();
  const title = source.title.toLowerCase();
  const matches = (domains: string[]) => domains.some((domain) => hostname === domain || hostname.endsWith(`.${domain}`));

  if (matches([
    "cloud.tencent.com", "tencentcloud.com", "aliyun.com", "aws.amazon.com",
    "azure.microsoft.com", "cloud.google.com",
  ]) || /腾讯云|阿里云|amazon web services|microsoft azure|google cloud/.test(title)) {
    return "cloud_platform";
  }
  if (source.source_type === "community") return "community";
  if (source.source_type === "campus") return "campus";
  if (source.source_type === "official") {
    return /product|products|platform|developer|产品|平台|开发者/.test(`${hostname} ${source.url.toLowerCase()} ${title}`)
      ? "official_product"
      : "official_company";
  }
  if (matches([
    "qbitai.com", "zhidx.com", "jiqizhixin.com", "leiphone.com", "infoq.cn",
    "hub.baai.ac.cn", "36kr.com", "venturebeat.com",
  ])) return "technology_media";
  if (matches([
    "stcn.com", "yicai.com", "caixin.com", "cls.cn", "jiemian.com", "eeo.com.cn",
    "thepaper.cn", "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com",
  ])) return "financial_media";
  return "technology_media";
}
