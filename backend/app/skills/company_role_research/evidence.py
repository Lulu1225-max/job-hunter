from __future__ import annotations

from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
import re

from app.skills.company_role_research.schemas import (
    EVIDENCE_TYPES_BY_SOURCE,
    Evidence,
    EvidenceType,
    FetchedSource,
)


IGNORED_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form", "aside"}
BLOCK_TAGS = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "article", "main"}
NOISE_MARKERS = {
    "cookie", "consent", "recommend", "related", "navigation", "breadcrumb", "advert",
    "share", "social", "popup", "modal", "newsletter", "推荐", "相关阅读", "猜你喜欢",
}


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0
        self._block_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = " ".join(value or "" for key, value in attrs if key in {"id", "class", "role"})
        is_noise = any(marker in attributes.casefold() for marker in NOISE_MARKERS)
        if self._ignored_depth or tag in IGNORED_TAGS or is_noise:
            self._ignored_depth += 1
            return
        if tag in BLOCK_TAGS:
            self._block_depth += 1
            self.parts.append("\n")
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag in BLOCK_TAGS:
            self._block_depth = max(0, self._block_depth - 1)
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._block_depth:
            self.parts.append(data)


def clean_html_text(html: str, *, max_length: int = 20_000) -> str:
    parser = _ReadableHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return ""
    lines: list[str] = []
    for part in "".join(parser.parts).splitlines():
        cleaned = re.sub(r"\s+", " ", part).strip()
        if cleaned and (not lines or cleaned != lines[-1]):
            lines.append(cleaned)
    return "\n".join(lines)[:max_length].strip()


EVIDENCE_KEYWORDS: dict[EvidenceType, tuple[str, ...]] = {
    "company": ("公司", "企业", "业务", "产品", "服务", "成立", "company", "business", "product"),
    "role": ("岗位", "职位", "职责", "要求", "任职", "role", "position", "responsibil", "requirement"),
    "recent_signal": (
        "发布", "宣布", "最新", "融资", "财报", "年报", "增长", "launch", "announce", "revenue",
        "agent", "智能体", "大模型", "llm", "工作流", "tool calling", "mcp", "rag", "知识管理", "办公协同", "流程自动化",
    ),
    "competitive": (
        "市场", "行业", "竞争", "份额", "对手", "竞品", "对标", "对比", "比较", "替代方案", "可比产品",
        "agent", "智能体", "agent platform", "agent os", "agent team", "workflow orchestration",
        "market", "industry", "competitor", "competition", "alternative", "comparison", "versus", " vs ", "share",
    ),
    "campus_recruitment": ("校园招聘", "校招", "应届", "实习", "网申", "招聘", "campus", "graduate", "intern"),
    "interview_experience": ("面经", "面试", "笔试", "一面", "二面", "终面", "interview", "assessment"),
}


class EvidenceExtractor:
    """Deterministically extracts bounded passages; it performs no generation."""

    def __init__(self, *, max_evidence_per_source: int = 6, max_evidence_length: int = 1_000) -> None:
        self.max_evidence_per_source = max(1, max_evidence_per_source)
        self.max_evidence_length = max(100, max_evidence_length)

    def extract(
        self,
        source: FetchedSource,
        *,
        company_name: str,
        job_title: str | None = None,
    ) -> list[Evidence]:
        if source.fetch_status != "success" or not source.extracted_text:
            return []
        allowed = EVIDENCE_TYPES_BY_SOURCE[source.source_type]
        passages = [line.strip() for line in source.extracted_text.splitlines() if len(line.strip()) >= 12]
        evidence: list[Evidence] = []
        seen: set[tuple[EvidenceType, str]] = set()
        for passage in passages:
            normalized = passage.casefold()
            for evidence_type in allowed:
                if evidence_type == "recent_signal" and not self._is_recent_publication(source.published_at):
                    continue
                if not self._matches(evidence_type, normalized, company_name, job_title):
                    continue
                text = passage[:self.max_evidence_length]
                key = (evidence_type, text)
                if key in seen:
                    continue
                seen.add(key)
                digest = sha256(f"{source.source_id}:{evidence_type}:{text}".encode()).hexdigest()[:20]
                evidence.append(Evidence(
                    evidence_id=f"evidence_{digest}",
                    source_id=source.source_id,
                    source_type=source.source_type,
                    evidence_type=evidence_type,
                    text=text,
                ))
                if len(evidence) >= self.max_evidence_per_source:
                    return evidence
        return evidence

    @staticmethod
    def _is_recent_publication(value: str | None, *, max_age_days: int = 90) -> bool:
        published = EvidenceExtractor._normalize_publication_date(value)
        if not published:
            return False
        today = date.today()
        return today - timedelta(days=max_age_days) <= published <= today

    @staticmethod
    def _normalize_publication_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return parsedate_to_datetime(value).date()
                except (TypeError, ValueError, OverflowError):
                    return None

    @staticmethod
    def _matches(
        evidence_type: EvidenceType,
        text: str,
        company_name: str,
        job_title: str | None,
    ) -> bool:
        if evidence_type == "company" and company_name.casefold() in text:
            return True
        if evidence_type == "role" and job_title and job_title.casefold() in text:
            return True
        return any(keyword in text for keyword in EVIDENCE_KEYWORDS[evidence_type])
