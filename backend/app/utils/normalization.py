from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", " ", text).lower()


def display_text(value: Any) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return text or None


def canonical_status(value: str | None) -> str:
    normalized = normalize_text(value)
    aliases = {
        "saved": "saved",
        "收藏": "saved",
        "applied": "applied",
        "已投递": "applied",
        "oa": "oa",
        "online assessment": "oa",
        "笔试": "oa",
        "interview": "interview",
        "面试": "interview",
        "final interview": "final_interview",
        "终面": "final_interview",
        "offer": "offer",
        "录用": "offer",
        "rejected": "rejected",
        "拒绝": "rejected",
        "withdrawn": "withdrawn",
        "撤回": "withdrawn",
    }
    return aliases.get(normalized, "saved")


def canonical_job_type(value: Any) -> str | None:
    normalized = normalize_text(value)
    if not normalized:
        return None
    if any(token in normalized for token in ["实习", "intern"]):
        return "internship"
    if any(token in normalized for token in ["正式", "校招", "graduate", "new grad"]):
        return "graduate"
    if "full" in normalized:
        return "full_time"
    return normalized.replace(" ", "_")


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = display_text(value)
    if not text:
        return None
    if "招满" in text or "rolling" in normalize_text(text):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
