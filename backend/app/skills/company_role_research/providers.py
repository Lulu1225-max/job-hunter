from __future__ import annotations

from datetime import date, datetime, timedelta
from dataclasses import replace
from email.utils import parsedate_to_datetime
import re
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.skills.company_role_research.schemas import WebSearchSource, WebSourceType
from app.skills.company_role_research.competitive_discovery import (
    AI_MARKET_DIMENSIONS,
    CORE_MARKET_DIMENSIONS,
    CompetitiveCandidateMetadata,
    candidate_entity_type,
    candidate_priority,
    candidate_entity_key,
    discover_entity,
    discovery_query_terms,
    infer_competitive_dimensions,
    is_specific_candidate_entity,
    market_seed_terms,
    market_overlap_dimensions,
    select_diverse_candidates,
    shared_dimensions,
)


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
CHINA_BUSINESS_NEWS_DOMAINS = {
    "stcn.com": 10,       # 证券时报
    "yicai.com": 20,      # 第一财经
    "caixin.com": 30,     # 财新
    "cls.cn": 40,         # 财联社
    "jiemian.com": 50,    # 界面新闻
    "36kr.com": 60,       # 36氪
    "eeo.com.cn": 70,     # 经济观察报
    "thepaper.cn": 80,    # 澎湃新闻 / 澎湃财经
    "finance.sina.com.cn": 85,  # 新浪财经（仅作为公开商业媒体来源）
}
CHINA_AI_TECH_DOMAINS = {
    "qbitai.com": 90,        # 量子位
    "zhidx.com": 95,         # 智东西
    "jiqizhixin.com": 100,   # 机器之心
    "leiphone.com": 105,     # 雷峰网
    "infoq.cn": 110,         # InfoQ 中文
    "hub.baai.ac.cn": 115,   # 北京智源社区公开内容
    "tmtpost.com": 116,      # 钛媒体科技公开内容
    "cww.net.cn": 117,       # 通信世界网
}
TRUSTED_PRODUCT_TECH_DOMAINS = {
    "adp.tencent.com": 120,   # 腾讯云开发者 / 产品公开资料
    "tencentcloud.com": 120,  # 腾讯云官方产品公开资料
    "help.aliyun.com": 125,   # 阿里云官方产品文档
}
INTERNATIONAL_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "ft.com", "bloomberg.com",
    "wsj.com", "theguardian.com", "cnbc.com", "abc.net.au", "afr.com", "forbes.com",
    "venturebeat.com",
}
TRUSTED_NEWS_DOMAINS = (
    set(CHINA_BUSINESS_NEWS_DOMAINS)
    | set(CHINA_AI_TECH_DOMAINS)
    | set(TRUSTED_PRODUCT_TECH_DOMAINS)
    | INTERNATIONAL_NEWS_DOMAINS
)
CAMPUS_DOMAINS = {"nowcoder.com"}
COMMUNITY_DOMAINS = {"nowcoder.com"}
UNTRUSTED_COMMUNITY_DOMAINS = {"zhihu.com", "xiaohongshu.com"}
NON_OFFICIAL_DOMAINS = TRUSTED_NEWS_DOMAINS | CAMPUS_DOMAINS | UNTRUSTED_COMMUNITY_DOMAINS | {
    "wikipedia.org", "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "glassdoor.com", "indeed.com", "crunchbase.com",
}


class CompanyResearchProvider(Protocol):
    """Search-only boundary. Results are candidates, not verified report facts."""

    def search_company_official(self, company_name: str) -> list[WebSearchSource]: ...
    def search_company_profile(self, company_name: str, query: str) -> list[WebSearchSource]: ...
    def search_company_careers(self, company_name: str) -> list[WebSearchSource]: ...
    def search_recent_news(self, company_name: str, job_title: str | None = None, saved_jd: str | None = None) -> list[WebSearchSource]: ...
    def search_competitive_references(self, company_name: str, job_title: str | None = None, saved_jd: str | None = None) -> list[WebSearchSource]: ...
    def search_campus_recruitment(self, company_name: str) -> list[WebSearchSource]: ...
    def search_interview_experience(
        self,
        company_name: str,
        job_title: str | None = None,
    ) -> list[WebSearchSource]: ...


class EmptyCompanyResearchProvider:
    """Production-safe phase-one provider: it never claims external facts."""

    def search_company_official(self, company_name: str) -> list[WebSearchSource]:
        return []

    def search_company_profile(self, company_name: str, query: str) -> list[WebSearchSource]:
        return []

    def search_company_careers(self, company_name: str) -> list[WebSearchSource]:
        return []

    def search_recent_news(self, company_name: str, job_title: str | None = None, saved_jd: str | None = None) -> list[WebSearchSource]:
        return []

    def search_competitive_references(self, company_name: str, job_title: str | None = None, saved_jd: str | None = None) -> list[WebSearchSource]:
        return []

    def search_campus_recruitment(self, company_name: str) -> list[WebSearchSource]:
        return []

    def search_interview_experience(
        self,
        company_name: str,
        job_title: str | None = None,
    ) -> list[WebSearchSource]:
        return []


class TavilyCompanyResearchProvider:
    """Tavily-backed source discovery without page fetching or summarization."""

    def __init__(
        self,
        api_key: str,
        *,
        top_n: int = 3,
        recent_days: int = 90,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Tavily Search API key is required")
        self.api_key = api_key
        self.top_n = min(max(top_n, 1), 5)
        self.recent_days = min(max(recent_days, 1), 365)
        self.client = client or httpx.Client(timeout=10.0)
        self._official_domains: dict[str, set[str]] = {}
        self._official_source_context: dict[str, list[WebSearchSource]] = {}
        self._recruitment_results: dict[str, list[dict[str, Any]]] = {}
        self._recent_candidate_pools: dict[str, list[WebSearchSource]] = {}
        self._competitive_candidate_metadata: dict[str, dict[str, CompetitiveCandidateMetadata]] = {}
        self._competitive_candidate_alternatives: dict[str, dict[str, list[WebSearchSource]]] = {}
        self._competitive_verification_metadata: dict[str, dict[str, dict[str, Any]]] = {}
        self._competitive_qualification_diagnostics: dict[str, list[dict[str, Any]]] = {}
        self._competitive_diagnostics: dict[str, dict[str, int]] = {}

    def search_company_official(self, company_name: str) -> list[WebSearchSource]:
        results = self._search(
            f'{company_name} 官方 关于我们 公司简介 核心业务 产品生态 投资者关系 年报'
        )
        direct_matches = [item for item in results if self._is_official_candidate(item, company_name)]
        organization_domains = {
            self._registrable_domain(self._hostname(str(item.get("url") or "")))
            for item in direct_matches
            if self._hostname(str(item.get("url") or ""))
        }
        official = [
            item for item in results
            if item in direct_matches
            or self._matches_domain(
                self._hostname(str(item.get("url") or "")),
                organization_domains,
            )
        ]
        official.sort(key=self._official_page_rank)
        # Keep a wider pool from the same single search so the profile workflow
        # can choose complementary overview/IR/platform/product pages.
        sources = self._to_sources(official, "official", limit=10)
        discovered_domains: set[str] = set()
        for source in sources:
            host = self._hostname(source.url)
            if host:
                discovered_domains.add(host)
                discovered_domains.add(self._registrable_domain(host))
        self._official_domains[self._key(company_name)] = discovered_domains
        self._official_source_context[self._key(company_name)] = list(sources)
        return sources[:self.top_n]

    def search_company_profile(self, company_name: str, query: str) -> list[WebSearchSource]:
        """One bounded discovery call for official-first Company Profile research."""
        results = self._search(query, candidate_limit=15)
        key = self._key(company_name)
        known_domains = self._official_domains.get(key, set())
        official_context = self._official_source_context.get(key, [])
        primary_domain = (
            self._registrable_domain(self._hostname(official_context[0].url))
            if official_context else ""
        )
        organization_domains = {
            domain for domain in known_domains
            if not primary_domain or self._registrable_domain(domain) == primary_domain
        }
        official_results: list[dict[str, Any]] = []
        trusted_external: list[dict[str, Any]] = []
        for item in results:
            host = self._hostname(str(item.get("url") or ""))
            if (
                self._matches_domain(host, organization_domains)
                if organization_domains
                else self._is_official_candidate(item, company_name)
            ):
                official_results.append(item)
            elif self._matches_domain(host, TRUSTED_NEWS_DOMAINS):
                trusted_external.append(item)
        official_results.sort(key=self._official_page_rank)
        official_sources = self._to_sources(official_results, "official", limit=12)
        discovered_domains = set(organization_domains or known_domains)
        for source in official_sources:
            host = self._hostname(source.url)
            if host:
                discovered_domains.update({host, self._registrable_domain(host)})
        self._official_domains[self._key(company_name)] = discovered_domains
        external_sources = self._to_sources(trusted_external, "external", limit=4)
        return [*official_sources, *external_sources]

    def get_official_source_pool(self, company_name: str) -> list[WebSearchSource]:
        return list(self._official_source_context.get(self._key(company_name), []))

    def search_company_careers(self, company_name: str) -> list[WebSearchSource]:
        domains = self._official_domains.get(self._key(company_name))
        if domains is None:
            self.search_company_official(company_name)
            domains = self._official_domains.get(self._key(company_name), set())
        results = self._ensure_recruitment_results(company_name)
        careers = [
            item for item in results
            if self._matches_domain(self._hostname(str(item.get("url", ""))), domains)
            and re.search(
                r"career|jobs|join|work-with|vacanc|招聘|校招|应届|实习",
                f'{item.get("title", "")} {item.get("url", "")}',
                re.I,
            )
        ]
        return self._to_sources(careers, "official")

    def search_recent_news(self, company_name: str, job_title: str | None = None, saved_jd: str | None = None) -> list[WebSearchSource]:
        role_terms = self._role_aware_news_terms(job_title, saved_jd)
        role_query = " OR ".join(f'"{term}"' if " " in term else term for term in role_terms)
        comparison_terms = "最新 OR 动态 OR 发布 OR 更新"
        results = self._search(
            f'"{company_name}" ({role_query}) ({comparison_terms})'.strip(),
            topic="general",
            candidate_limit=15,
        )
        official_domains = self._official_domains.get(self._key(company_name), set())
        ranked_sources: list[tuple[int, WebSearchSource]] = []
        for item in results:
            host = self._hostname(str(item.get("url", "")))
            if self._matches_domain(host, official_domains):
                source_type = "official"
                rank = 0
            elif self._matches_domain(host, TRUSTED_NEWS_DOMAINS):
                source_type = "external"
                rank = self._news_rank(host, company_name)
            else:
                continue
            source = self._to_sources([item], source_type, limit=1)
            if source:
                role_score = self._role_news_score(item, role_terms)
                competitive_score = self._competitive_discovery_score(item)
                company_score = self._target_company_score(item, company_name)
                date_score = self._publication_recency_score(source[0].published_at)
                ranked_sources.append((rank - role_score - competitive_score - company_score - date_score, source[0]))
        ranked_sources.sort(key=lambda entry: entry[0])
        pool = [source for _, source in ranked_sources]
        self._recent_candidate_pools[self._key(company_name)] = pool
        return pool[:self.top_n]

    def search_competitive_references(
        self,
        company_name: str,
        job_title: str | None = None,
        saved_jd: str | None = None,
    ) -> list[WebSearchSource]:
        dimensions = infer_competitive_dimensions(job_title, saved_jd)
        if not dimensions:
            self._competitive_candidate_metadata[self._key(company_name)] = {}
            self._competitive_candidate_alternatives[self._key(company_name)] = {}
            self._competitive_verification_metadata[self._key(company_name)] = {}
            self._competitive_qualification_diagnostics[self._key(company_name)] = []
            self._competitive_diagnostics[self._key(company_name)] = {
                "competitive_dimensions_count": 0,
                "candidate_discovered_count": 0,
                "candidate_selected_count": 0,
                "candidate_rejected_count": 0,
            }
            return []
        key = self._key(company_name)
        official_context = " ".join(
            f"{source.title} {source.snippet}"
            for source in self._official_source_context.get(key, [])
        )
        market_context = f"{job_title or ''} {saved_jd or ''} {official_context}"
        target_market_dimensions = set(market_overlap_dimensions(market_context))
        market_terms: list[str] = []
        ai_terms: list[str] = []
        if "consumer_smart_device" in target_market_dimensions:
            market_terms.extend([
                "smartphone manufacturers", "smart device brands", "mobile device companies",
                "手机厂商", "智能终端品牌",
            ])
        if "automotive_intelligent_cockpit" in target_market_dimensions:
            market_terms.extend(["automotive intelligent cockpit brands", "智能座舱厂商"])
        if "ai_assistant" in target_market_dimensions:
            ai_terms.extend(["AI assistant", "mobile AI assistant", "智能助手"])
        if "cross_device_ai" in target_market_dimensions:
            ai_terms.extend(["cross-device AI ecosystem", "跨设备 AI 生态"])
        if "agent_platform" in target_market_dimensions:
            ai_terms.extend(["consumer AI Agent product", "AI Agent 产品"])
        if "enterprise_workflow" in target_market_dimensions:
            market_terms.extend(["enterprise software products", "企业软件产品"])
            ai_terms.extend(["enterprise AI workflow", "企业 AI 工作流"])
        if not market_terms:
            market_terms = market_seed_terms(job_title, saved_jd, dimensions, official_context)[:4]
        if not ai_terms:
            ai_terms = discovery_query_terms(dimensions)[:4]
        paired_clauses: list[str] = []
        if "consumer_smart_device" in target_market_dimensions:
            paired_clauses.extend([
                '"smartphone brand" "AI assistant" official product',
                '"smart device brand" "cross-device AI" official',
                '"手机厂商" "AI 助手" 官方产品',
                '"智能终端品牌" "跨设备 AI" 官方',
            ])
        if "automotive_intelligent_cockpit" in target_market_dimensions:
            paired_clauses.extend([
                '"automotive brand" "AI assistant" "intelligent cockpit" official',
                '"汽车品牌" "智能助手" "智能座舱" 官方',
            ])
        if "enterprise_workflow" in target_market_dimensions and not paired_clauses:
            paired_clauses.extend([
                '"enterprise software product" "AI Agent" official',
                '"企业软件产品" "AI 工作流" 官方',
            ])
        if not paired_clauses:
            market_query = " OR ".join(f'"{term}"' for term in dict.fromkeys(market_terms))
            ai_query = " OR ".join(f'"{term}"' for term in dict.fromkeys(ai_terms))
            paired_clauses.append(f"({market_query}) ({ai_query})")
        results = self._search(
            " OR ".join(f"({clause})" for clause in paired_clauses),
            candidate_limit=20,
        )
        results = self._diversify_market_peer_results(
            results, target_market_dimensions=target_market_dimensions,
        )
        search_pool = [
            {
                "title": source.title,
                "url": source.url,
                "content": source.snippet,
                "published_at": source.published_at,
            }
            for source in self._recent_candidate_pools.get(key, [])
        ]
        expanded_results: list[dict[str, Any]] = []
        for item in results:
            entities = self._extract_market_peer_entities(item)
            if not entities:
                expanded_results.append(item)
                continue
            for entity, context in entities:
                expanded_results.append({
                    **item,
                    "_candidate_entity": entity,
                    "content": context,
                })
        candidate_results = [
            *((item, "seeded") for item in expanded_results),
            *((item, "search") for item in search_pool),
        ]
        target_domains = self._official_domains.get(self._key(company_name), set())
        classified: list[tuple[WebSearchSource, CompetitiveCandidateMetadata, bool, str]] = []
        untrusted_discovery_urls: set[str] = set()
        rejected_non_entity_count = 0
        seeded_candidate_count = 0
        search_discovered_candidate_count = 0
        qualification_diagnostics: list[dict[str, Any]] = []
        for item, origin in candidate_results:
            url = str(item.get("url") or "")
            host = self._hostname(url)
            text = f'{item.get("title", "")} {item.get("content", "")} {url}'
            if self._matches_domain(host, target_domains):
                continue
            if re.search(r"/(?:event|events|training|course|courses|community|contribution|conference)(?:/|$)", url, re.I):
                rejected_entity = discover_entity(
                    str(item.get("title") or ""), str(item.get("content") or ""),
                )
                if not rejected_entity:
                    rejected_entity = re.sub(
                        r"\b(?:conference|summit|expo|exhibition)\b.*$|(?:大会|峰会|展会|论坛|博览会).*$",
                        "", str(item.get("title") or ""), flags=re.I,
                    ).strip(" -:|") or None
                if rejected_entity:
                    qualification_diagnostics.append({
                        "candidate_entity": rejected_entity,
                        "candidate_origin": origin,
                        "entity_type": candidate_entity_type(rejected_entity, text, is_official=False),
                        "shared_market_dimensions": [],
                        "shared_ai_dimensions": [],
                        "target_market_match": False,
                        "target_ai_match": False,
                        "market_overlap_score": 0,
                        "qualification_status": "reject",
                    })
                continue
            source = self._to_sources([item], "external", limit=1)
            if not source:
                continue
            entity = str(item.get("_candidate_entity") or "") or discover_entity(
                str(item.get("title") or ""), str(item.get("content") or ""),
            )
            if not entity or self._key(entity) == self._key(company_name):
                rejected_non_entity_count += 1
                continue
            compact_entity = re.sub(r"[^a-z0-9]", "", candidate_entity_key(entity))
            host_labels = {re.sub(r"[^a-z0-9]", "", label) for label in host.casefold().split(".")}
            entity_host_match = len(compact_entity) >= 3 and compact_entity in host_labels
            trusted_third_party = self._matches_domain(host, TRUSTED_NEWS_DOMAINS)
            looks_official = (
                not trusted_third_party
                and bool(host)
                and not self._matches_domain(host, NON_OFFICIAL_DOMAINS)
                and (
                    entity_host_match
                    or bool(re.search(r"official|官网|官方|developer|cloud|docs?", f'{item.get("title", "")} {url}', re.I))
                )
            )
            entity_type = candidate_entity_type(entity, text, is_official=looks_official)
            candidate_market_dimensions = set(market_overlap_dimensions(text))
            overlap = target_market_dimensions & candidate_market_dimensions
            metadata = candidate_priority(
                text=text,
                dimensions=dimensions,
                is_official_product_source=looks_official,
                entity=entity,
                candidate_origin=origin,
                market_context=market_context,
            )
            diagnostic = {
                "candidate_entity": entity,
                "candidate_origin": origin,
                "entity_type": entity_type,
                "shared_market_dimensions": sorted(overlap & CORE_MARKET_DIMENSIONS),
                "shared_ai_dimensions": sorted(overlap & AI_MARKET_DIMENSIONS),
                "target_market_match": bool(overlap & CORE_MARKET_DIMENSIONS),
                "target_ai_match": bool(overlap & AI_MARKET_DIMENSIONS),
                "market_overlap_score": (
                    len(overlap & CORE_MARKET_DIMENSIONS) * 50
                    + len(overlap & AI_MARKET_DIMENSIONS) * 20
                ),
                "qualification_status": metadata.qualification_status if metadata else "reject",
            }
            qualification_diagnostics.append(diagnostic)
            if metadata is not None:
                source_trusted = trusted_third_party or looks_official
                if not source_trusted and metadata.qualification_status != "primary_market_peer":
                    continue
                classified.append((source[0], metadata, looks_official, str(item.get("title") or "")))
                if not source_trusted:
                    untrusted_discovery_urls.add(source[0].url.rstrip("/"))
                if origin == "seeded":
                    seeded_candidate_count += 1
                else:
                    search_discovered_candidate_count += 1
        grouped: dict[str, list[tuple[WebSearchSource, CompetitiveCandidateMetadata, bool, str]]] = {}
        for entry in classified:
            grouped.setdefault(candidate_entity_key(entry[1].entity), []).append(entry)
        eligible: list[tuple[WebSearchSource, CompetitiveCandidateMetadata]] = []
        alternatives_by_primary: dict[str, list[WebSearchSource]] = {}
        for entries in grouped.values():
            entries.sort(key=lambda entry: entry[1].final_priority)
            primary_source, primary_metadata, _, _ = entries[0]
            has_official = any(entry[2] for entry in entries)
            if not is_specific_candidate_entity(
                primary_metadata.entity,
                title=entries[0][3],
                has_official_source=has_official,
                stable_result_count=len(entries),
            ):
                rejected_non_entity_count += len(entries)
                continue
            origins = {entry[1].candidate_origin for entry in entries}
            primary_metadata = replace(
                primary_metadata,
                candidate_origin="both" if len(origins) > 1 else next(iter(origins)),
                official_evidence_count=sum(entry[1].official_evidence_count for entry in entries),
                third_party_evidence_count=sum(entry[1].third_party_evidence_count for entry in entries),
                verification_success=True,
            )
            eligible.append((primary_source, primary_metadata))
            alternatives_by_primary[primary_source.url.rstrip("/")] = [entry[0] for entry in entries[1:]]
        selected = select_diverse_candidates(eligible, limit=self.top_n)
        primary_verification_targets = [
            entry for entry in selected
            if entry[1].qualification_status == "primary_market_peer"
        ]
        secondary_verification_targets = [
            entry for entry in selected
            if entry[1].qualification_status == "secondary_product_reference"
        ]
        verification_targets = (
            primary_verification_targets[:2]
            if primary_verification_targets
            else secondary_verification_targets[:2]
        )
        verification_results: list[dict[str, Any]] = []
        if verification_targets:
            clauses = []
            for _, metadata in verification_targets:
                dimensions_query = " OR ".join(metadata.shared_dimensions[:2])
                clauses.append(
                    f'"{metadata.entity}" ({dimensions_query}) '
                    "official product developer docs newsroom"
                )
            verification_results = self._search(
                " OR ".join(f"({clause})" for clause in clauses),
                candidate_limit=20,
            )
        verification_by_primary: dict[str, list[tuple[int, WebSearchSource]]] = {
            source.url.rstrip("/"): [] for source, _ in verification_targets
        }
        verification_metadata: dict[str, dict[str, Any]] = {}
        for primary_source, metadata in verification_targets:
            primary_url = primary_source.url.rstrip("/")
            primary_host = self._hostname(primary_source.url)
            primary_org_domain = self._registrable_domain(primary_host)
            aliases = {candidate_entity_key(metadata.entity)}
            if metadata.official_evidence_count:
                aliases.update(
                    label.casefold()
                    for label in primary_host.split(".")
                    if len(label) >= 3 and label.casefold() not in {"www", "com", "cn", "net", "org", "consumer"}
                )
            result_count = 0
            official_count = 0
            for item in verification_results:
                url = str(item.get("url") or "")
                host = self._hostname(url)
                normalized_url = url.rstrip("/")
                if not host or normalized_url == primary_url:
                    continue
                identity = candidate_entity_key(f'{item.get("title", "")} {host}')
                same_org_domain = bool(primary_org_domain) and self._registrable_domain(host) == primary_org_domain
                if not same_org_domain and not any(alias and alias in identity for alias in aliases):
                    continue
                text = f'{item.get("title", "")} {item.get("content", "")} {url}'
                if not (set(shared_dimensions(text, dimensions)) & set(metadata.shared_dimensions)):
                    continue
                trusted_media = self._matches_domain(host, TRUSTED_NEWS_DOMAINS)
                normalized_host = candidate_entity_key(host)
                entity_host_binding = any(alias and alias in normalized_host for alias in aliases)
                official = (
                    (
                        entity_host_binding
                        or (metadata.official_evidence_count > 0 and same_org_domain)
                    )
                    and not self._matches_domain(host, NON_OFFICIAL_DOMAINS)
                )
                if not official and not trusted_media:
                    continue
                source = self._to_sources([item], "external", limit=1)
                if not source:
                    continue
                result_count += 1
                official_count += int(official)
                trust_rank = 0 if official else (
                    20 if self._matches_domain(host, CHINA_AI_TECH_DOMAINS | TRUSTED_PRODUCT_TECH_DOMAINS)
                    else 30
                )
                verification_by_primary[primary_url].append((trust_rank, source[0]))
            verification_by_primary[primary_url].sort(key=lambda entry: entry[0])
            verification_metadata[primary_url] = {
                "verification_search_candidate": metadata.entity,
                "verification_query_category": metadata.market_candidate_type,
                "verification_result_count": result_count,
                "verification_official_source_count": official_count,
                "verification_source_urls": [
                    source.url.rstrip("/") for _, source in verification_by_primary[primary_url]
                ],
            }
        # Discovery-only pages are proposals, never evidence sources.  Promote
        # only a trusted Search-5 result to the selected source; otherwise the
        # candidate is rejected before fetch/generation.
        promoted_selected: list[tuple[WebSearchSource, CompetitiveCandidateMetadata]] = []
        promoted_verification: dict[str, list[tuple[int, WebSearchSource]]] = {}
        promoted_metadata: dict[str, dict[str, Any]] = {}
        for primary_source, metadata in selected:
            primary_url = primary_source.url.rstrip("/")
            if primary_url not in untrusted_discovery_urls:
                promoted_selected.append((primary_source, metadata))
                if primary_url in verification_by_primary:
                    promoted_verification[primary_url] = verification_by_primary[primary_url]
                if primary_url in verification_metadata:
                    promoted_metadata[primary_url] = verification_metadata[primary_url]
                continue
            verified = verification_by_primary.get(primary_url, [])
            if not verified:
                continue
            _, verified_primary = verified[0]
            verified_url = verified_primary.url.rstrip("/")
            promoted_selected.append((verified_primary, metadata))
            promoted_verification[verified_url] = verified[1:]
            promoted_metadata[verified_url] = {
                **verification_metadata.get(primary_url, {}),
                "verification_source_urls": [source.url.rstrip("/") for _, source in verified[1:]],
            }
            alternatives_by_primary[verified_url] = []
        selected = promoted_selected
        verification_by_primary = promoted_verification
        verification_metadata = promoted_metadata
        # Build acquisition fallbacks only after candidate selection.  This does
        # not propose or re-rank candidates: it reuses the existing Tavily pool
        # to find another page that is explicitly bound to the same entity and
        # covers at least one of the selected comparison dimensions.
        enriched_alternatives: dict[str, list[WebSearchSource]] = {}
        for primary_source, metadata in selected:
            primary_url = primary_source.url.rstrip("/")
            primary_host = self._hostname(primary_source.url)
            aliases = {
                candidate_entity_key(metadata.entity),
                *(
                    label.casefold()
                    for label in primary_host.split(".")
                    if len(label) >= 3 and label.casefold() not in {"www", "com", "cn", "net", "org"}
                ),
            }
            ranked_alternatives: list[tuple[int, WebSearchSource]] = []
            seen_urls = {primary_url}
            for source, source_metadata, looks_official, source_title in classified:
                normalized_url = source.url.rstrip("/")
                if normalized_url in seen_urls:
                    continue
                source_identity = candidate_entity_key(
                    f"{source_title} {urlparse(source.url).netloc}"
                )
                same_entity = (
                    candidate_entity_key(source_metadata.entity) == candidate_entity_key(metadata.entity)
                    or any(alias and alias in source_identity for alias in aliases)
                )
                same_dimension = bool(
                    set(source_metadata.shared_dimensions) & set(metadata.shared_dimensions)
                )
                if not same_entity or not same_dimension:
                    continue
                host = self._hostname(source.url)
                path_text = f"{source_title} {source.url}".casefold()
                if looks_official:
                    trust_rank = 0
                    if re.search(r"developer|docs?|cloud|news|press|media| newsroom", path_text, re.I):
                        trust_rank -= 5
                elif self._matches_domain(host, CHINA_AI_TECH_DOMAINS | TRUSTED_PRODUCT_TECH_DOMAINS):
                    trust_rank = 20
                elif self._matches_domain(host, TRUSTED_NEWS_DOMAINS):
                    trust_rank = 30
                else:
                    continue
                dimension_penalty = len(metadata.shared_dimensions) - len(
                    set(source_metadata.shared_dimensions) & set(metadata.shared_dimensions)
                )
                ranked_alternatives.append((trust_rank + dimension_penalty, source))
                seen_urls.add(normalized_url)
            ranked_alternatives.sort(key=lambda entry: entry[0])
            existing = alternatives_by_primary.get(primary_url, [])
            combined: list[WebSearchSource] = []
            verification_sources = [
                source for _, source in verification_by_primary.get(primary_url, [])
            ]
            for source in [*existing, *verification_sources, *(source for _, source in ranked_alternatives)]:
                if source.url.rstrip("/") not in {item.url.rstrip("/") for item in combined}:
                    combined.append(source)
            enriched_alternatives[primary_url] = combined
        self._competitive_candidate_metadata[key] = {
            source.url.rstrip("/"): metadata for source, metadata in selected
        }
        self._competitive_candidate_alternatives[key] = {
            source.url.rstrip("/"): enriched_alternatives.get(source.url.rstrip("/"), [])
            for source, _ in selected
        }
        self._competitive_verification_metadata[key] = verification_metadata
        self._competitive_qualification_diagnostics[key] = qualification_diagnostics
        self._competitive_diagnostics[key] = {
            "competitive_dimensions_count": len(dimensions),
            "candidate_discovered_count": len(results),
            "candidate_selected_count": len(selected),
            "candidate_rejected_count": max(0, len(candidate_results) - len(selected)),
            "rejected_non_entity_count": rejected_non_entity_count,
            "seeded_candidate_count": seeded_candidate_count,
            "search_discovered_candidate_count": search_discovered_candidate_count,
            "merged_candidate_count": len(eligible),
            "market_peer_search_result_count": len(results),
            "extracted_company_candidate_count": sum(
                item["entity_type"] == "company" for item in qualification_diagnostics
            ),
            "extracted_branded_ai_product_count": sum(
                item["entity_type"] in {"branded_product", "branded_platform"}
                and item["target_ai_match"] for item in qualification_diagnostics
            ),
            "primary_market_peer_count": sum(
                item["qualification_status"] == "primary_market_peer"
                for item in qualification_diagnostics
            ),
            "secondary_candidate_count": sum(
                item["qualification_status"] == "secondary_product_reference"
                for item in qualification_diagnostics
            ),
        }
        return [source for source, _ in selected]

    def get_competitive_candidate_metadata(self, company_name: str) -> dict[str, CompetitiveCandidateMetadata]:
        return dict(self._competitive_candidate_metadata.get(self._key(company_name), {}))

    def get_competitive_candidate_alternatives(self, company_name: str) -> dict[str, list[WebSearchSource]]:
        return {
            url: list(sources)
            for url, sources in self._competitive_candidate_alternatives.get(self._key(company_name), {}).items()
        }

    def get_competitive_verification_metadata(self, company_name: str) -> dict[str, dict[str, Any]]:
        return {
            url: dict(metadata)
            for url, metadata in self._competitive_verification_metadata.get(self._key(company_name), {}).items()
        }

    def get_competitive_qualification_diagnostics(self, company_name: str) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self._competitive_qualification_diagnostics.get(self._key(company_name), [])
        ]

    def get_competitive_diagnostics(self, company_name: str) -> dict[str, int]:
        return dict(self._competitive_diagnostics.get(self._key(company_name), {}))

    def get_recent_candidate_pool(self, company_name: str) -> list[WebSearchSource]:
        """Return trusted candidates from the existing Tavily response; performs no search."""
        return list(self._recent_candidate_pools.get(self._key(company_name), []))

    @classmethod
    def _diversify_market_peer_results(
        cls,
        results: list[dict[str, Any]],
        *,
        target_market_dimensions: set[str],
    ) -> list[dict[str, Any]]:
        """Rank market+AI matches and limit repeated domains; snippets stay discovery-only."""
        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for index, item in enumerate(results):
            text = f'{item.get("title", "")} {item.get("content", "")}'
            overlap = set(market_overlap_dimensions(text)) & target_market_dimensions
            market_match = bool(overlap & CORE_MARKET_DIMENSIONS)
            ai_match = bool(overlap & AI_MARKET_DIMENSIONS)
            is_event = candidate_entity_type("candidate", text, is_official=False) == "event"
            score = (
                80 if market_match and ai_match
                else 30 if market_match
                else 10 if ai_match
                else 0
            ) - (100 if is_event else 0)
            ranked.append((-score, index, item))
        ranked.sort(key=lambda entry: (entry[0], entry[1]))
        domain_counts: dict[str, int] = {}
        diverse: list[dict[str, Any]] = []
        for _, _, item in ranked:
            domain = cls._registrable_domain(cls._hostname(str(item.get("url") or "")))
            if domain and domain_counts.get(domain, 0) >= 2:
                continue
            diverse.append(item)
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        return diverse

    @staticmethod
    def _extract_market_peer_entities(item: dict[str, Any]) -> list[tuple[str, str]]:
        """Extract one conservative brand proposal from a discovery result.

        Search snippets are useful for proposing a market peer, but a single result
        must not fan out into every capitalised word in its title or snippet.  The
        selected proposal is still discovery-only and must pass the existing entity,
        market-overlap, and verification stages before it can provide evidence.
        """
        title = str(item.get("title") or "")
        content = str(item.get("content") or "")
        text = f"{title}. {content}"
        generic = {
            "the", "best", "top", "new", "latest", "official", "global", "world",
            "ai", "phone", "phones", "smartphone", "smartphones", "mobile", "brand",
            "brands", "assistant", "assistants", "agent", "agents", "platform", "workflow",
            "cloud", "powered", "features", "review", "reviews", "real", "meet",
            "logo", "news", "media", "this", "that", "these", "those", "among",
            "during", "published", "report", "reports", "pro", "ultra", "max",
            "plus", "series", "edge", "step", "gui", "api", "sdk", "ieee",
            "waic", "am oled", "amoled", "ltpo", "aos", "saep",
        }
        market_followers = {
            "galaxy", "find", "coloros", "assistant", "phone", "smartphone",
            "mobile", "device", "devices", "ai", "ecosystem",
        }
        candidates: list[tuple[int, str, int]] = []
        for match in re.finditer(r"\b[A-Z][A-Za-z0-9.-]{2,24}\b", text):
            entity = match.group(0).strip(".-")
            if entity.casefold() in generic:
                continue
            occurrences = len(re.findall(rf"\b{re.escape(entity)}\b", text, re.I))
            following = text[match.end():match.end() + 32].casefold().split()
            is_all_caps = entity.isupper() and entity.isalpha() and 3 <= len(entity) <= 10
            is_camel_case = bool(re.search(r"[a-z][A-Z]", entity))
            has_market_follower = bool(following and following[0].strip(".,:;()") in market_followers)
            if not (is_all_caps or is_camel_case or occurrences >= 2 or has_market_follower):
                continue
            score = (
                (90 if is_all_caps else 0)
                + (85 if is_camel_case else 0)
                + (40 if occurrences >= 2 else 0)
                + (30 if has_market_follower else 0)
            )
            candidates.append((score, entity, match.start()))
        for match in re.finditer(
            r"([\u3400-\u9fff]{2,8})(?=(?:的)?(?:AI\s*助手|智能助手|手机品牌|手机厂商|智能终端))",
            content, re.I,
        ):
            entity = match.group(1)
            if not re.search(r"这个|一种|多个|品牌|厂商|全球|首款|手机|智能", entity):
                candidates.append((100, entity, len(title) + 2 + match.start()))
        discovered = discover_entity(title, content)
        if not candidates and discovered and discovered.casefold() not in generic:
            location = text.casefold().find(discovered.casefold())
            candidates.append((20, discovered, max(location, 0)))
        if not candidates:
            return []
        _, entity, position = max(candidates, key=lambda candidate: candidate[0])
        if not candidate_entity_key(entity):
            return []
        start = max(0, position - 160)
        end = min(len(text), position + len(entity) + 220)
        return [(entity, text[start:end])]

    @staticmethod
    def _role_aware_news_terms(job_title: str | None, saved_jd: str | None) -> list[str]:
        context = f"{job_title or ''} {saved_jd or ''}".casefold()
        terms: list[str] = []
        if re.search(r"ai|agent|智能体|大模型|llm|人工智能", context, re.I):
            terms.extend(["AI Agent", "大模型", "LLM", "工作流"])
        elif job_title:
            terms.extend([job_title, f"{job_title} 产品", f"{job_title} 业务"])
        return terms[:4]

    @staticmethod
    def _role_news_score(item: dict[str, Any], role_terms: list[str]) -> int:
        text = f'{item.get("title", "")} {item.get("content", "")}'.casefold()
        ai_anchors = ("agent", "智能体", "大模型", "llm", "工作流", "tool", "skill", "mcp", "rag", "知识管理", "办公协同", "流程自动化", "ai 产品")
        low_anchors = ("手机新品", "手机发布", "销量", "财报", "芯片出货", "汽车销量", "市场份额")
        score = sum(30 for anchor in ai_anchors if anchor in text)
        score += sum(15 for term in role_terms if any(token in text for token in term.casefold().split()))
        score -= sum(35 for anchor in low_anchors if anchor in text)
        return score

    @staticmethod
    def _competitive_discovery_score(item: dict[str, Any]) -> int:
        text = f'{item.get("title", "")} {item.get("content", "")}'.casefold()
        explicit_markers = (
            "对标", "对比", "比较", "竞品", "相比", "versus", " vs ",
            "compare", "compared", "comparison", "alternative", "competitor", "rivals", "beats",
        )
        return 600 if any(marker in text for marker in explicit_markers) else 0

    def search_campus_recruitment(self, company_name: str) -> list[WebSearchSource]:
        domains = self._official_domains.get(self._key(company_name))
        if domains is None:
            self.search_company_official(company_name)
            domains = self._official_domains.get(self._key(company_name), set())
        results = self._ensure_recruitment_results(company_name)
        ranked_sources: list[tuple[int, WebSearchSource]] = []
        for item in results:
            host = self._hostname(str(item.get("url", "")))
            if self._matches_domain(host, domains):
                source_type = "official"
                rank = 0
            elif self._matches_domain(host, CAMPUS_DOMAINS):
                if not re.search(
                    r"校园招聘|校招|实习|应届|招聘|enterprise|job",
                    f'{item.get("title", "")} {item.get("url", "")}',
                    re.I,
                ):
                    continue
                source_type = "campus"
                rank = 10
            else:
                continue
            source = self._to_sources([item], source_type, limit=1)
            if source:
                ranked_sources.append((rank, source[0]))
        ranked_sources.sort(key=lambda entry: entry[0])
        return [source for _, source in ranked_sources[:self.top_n]]

    def search_interview_experience(
        self,
        company_name: str,
        job_title: str | None = None,
    ) -> list[WebSearchSource]:
        results = self._ensure_recruitment_results(company_name, job_title)
        community = [
            item for item in results
            if self._matches_domain(self._hostname(str(item.get("url", ""))), COMMUNITY_DOMAINS)
            and re.search(
                r"面经|面试经验|interview|discuss",
                f'{item.get("title", "")} {item.get("url", "")}',
                re.I,
            )
        ]
        return self._to_sources(community, "community")

    def _ensure_recruitment_results(
        self,
        company_name: str,
        job_title: str | None = None,
    ) -> list[dict[str, Any]]:
        key = self._key(company_name)
        if key not in self._recruitment_results:
            role = f' "{job_title}"' if job_title else ""
            self._recruitment_results[key] = self._search(
                f'"{company_name}"{role} 招聘 校园招聘 校招 实习 应届生 面经 面试经验 牛客'
            )
        return self._recruitment_results[key]

    def _search(
        self,
        query: str,
        *,
        topic: str = "general",
        start_date: str | None = None,
        end_date: str | None = None,
        prefer_domains: set[str] | None = None,
        candidate_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "query": query,
            "search_depth": "basic",
            "max_results": min(candidate_limit or self.top_n * 3, 20),
            "topic": topic,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_published_date": True,
            "safe_search": True,
        }
        if topic == "general":
            payload.update({"country": "china", "language": "zh-cn"})
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
        if start_date or end_date:
            payload["filter_by_published_date"] = True
        if prefer_domains:
            payload.update({
                "include_domains": sorted(prefer_domains),
                "include_domains_mode": "prefer",
            })
        try:
            response = self.client.post(
                TAVILY_SEARCH_URL,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        results = payload.get("results", [])
        return results if isinstance(results, list) else []

    def _to_sources(
        self,
        results: list[dict[str, Any]],
        source_type: WebSourceType,
        *,
        limit: int | None = None,
    ) -> list[WebSearchSource]:
        sources: list[WebSearchSource] = []
        seen: set[str] = set()
        for item in results:
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url.startswith(("http://", "https://")) or not title or url in seen:
                continue
            seen.add(url)
            sources.append(WebSearchSource(
                title=title,
                url=url,
                snippet=str(item.get("content") or "").strip(),
                published_at=self._published_at(item),
                source_type=source_type,
            ))
            if len(sources) >= (limit or self.top_n):
                break
        return sources

    def _is_official_candidate(self, item: dict[str, Any], company_name: str) -> bool:
        url = str(item.get("url") or "")
        host = self._hostname(url)
        if not host or self._matches_domain(host, NON_OFFICIAL_DOMAINS):
            return False
        normalized_company = self._key(company_name)
        normalized_host = re.sub(r"[^a-z0-9]", "", host)
        normalized_title = self._key(str(item.get("title") or ""))
        company_tokens = [token for token in normalized_company.split() if len(token) > 2]
        return normalized_company in normalized_title or any(token in normalized_host for token in company_tokens)

    @staticmethod
    def _published_at(item: dict[str, Any]) -> str | None:
        value = item.get("published_at") or item.get("published_date") or item.get("date")
        if not value:
            return None
        text = str(value).strip()
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(text).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _official_page_rank(item: dict[str, Any]) -> tuple[int, str]:
        text = f'{item.get("title", "")} {item.get("url", "")} {item.get("content", "")}'.casefold()
        priorities = (
            (0, ("about", "company-profile", "corporate-profile", "公司介绍", "关于我们", "集团介绍")),
            (1, ("products", "business", "ecosystem", "产品", "业务", "生态")),
            (2, ("investor", "annual-report", "annual report", "ir.", "投资者", "年报")),
            (3, ("corporate", "profile", "企业简介", "公司概况")),
            (4, ("career", "careers", "jobs", "招聘", "加入我们")),
            (5, ("platform", "developer", "平台", "开发者")),
            (9, ("news", "新闻", "公告")),
        )
        rank = next((rank for rank, markers in priorities if any(marker in text for marker in markers)), 7)
        return rank, str(item.get("url") or "")

    @staticmethod
    def _target_company_score(item: dict[str, Any], company_name: str) -> int:
        text = f'{item.get("title", "")} {item.get("content", "")}'.casefold()
        return 180 if company_name.casefold() in text else 0

    @staticmethod
    def _publication_recency_score(value: str | None) -> int:
        if not value:
            return 0
        try:
            published = date.fromisoformat(value)
        except ValueError:
            return 0
        age = date.today() - published
        if timedelta(0) <= age <= timedelta(days=90):
            return 140
        return -80

    @staticmethod
    def _key(value: str) -> str:
        return " ".join(re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE))

    @staticmethod
    def _hostname(url: str) -> str:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")

    @staticmethod
    def _matches_domain(host: str, domains: set[str]) -> bool:
        return any(host == domain or host.endswith(f".{domain}") for domain in domains)

    @classmethod
    def _news_rank(cls, host: str, company_name: str) -> int:
        domestic_rank = next(
            (
                rank
                for domain, rank in CHINA_BUSINESS_NEWS_DOMAINS.items()
                if cls._matches_domain(host, {domain})
            ),
            None,
        )
        if domestic_rank is not None:
            return domestic_rank
        ai_tech_rank = next(
            (
                rank
                for domain, rank in CHINA_AI_TECH_DOMAINS.items()
                if cls._matches_domain(host, {domain})
            ),
            None,
        )
        if ai_tech_rank is not None:
            return ai_tech_rank
        product_tech_rank = next(
            (
                rank
                for domain, rank in TRUSTED_PRODUCT_TECH_DOMAINS.items()
                if cls._matches_domain(host, {domain})
            ),
            None,
        )
        if product_tech_rank is not None:
            return product_tech_rank
        international_rank = 200
        return international_rank if cls._is_chinese_company(company_name) else 100

    @staticmethod
    def _is_chinese_company(company_name: str) -> bool:
        return bool(re.search(r"[\u3400-\u9fff]", company_name))

    @staticmethod
    def _registrable_domain(host: str) -> str:
        """Return a conservative organization-domain key for sibling subdomains."""
        labels = [label for label in host.casefold().strip(".").split(".") if label]
        if len(labels) <= 2:
            return ".".join(labels)
        if ".".join(labels[-2:]) in {"com.cn", "net.cn", "org.cn", "gov.cn"}:
            return ".".join(labels[-3:])
        return ".".join(labels[-2:])


def create_company_research_provider(api_key: str | None) -> CompanyResearchProvider:
    if not api_key:
        return EmptyCompanyResearchProvider()
    return TavilyCompanyResearchProvider(api_key)
