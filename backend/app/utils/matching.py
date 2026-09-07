from __future__ import annotations

import hashlib
from typing import Iterable

from app.utils.normalization import normalize_text


def source_fingerprint(values: Iterable[str | None]) -> str:
    normalized = [normalize_text(value) for value in values if normalize_text(value)]
    digest_input = "|".join(normalized)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def case_insensitive_contains(haystack: str | None, needle: str | None) -> bool:
    return normalize_text(needle) in normalize_text(haystack)


def score_skill_overlap(required: list[str], owned: list[str]) -> tuple[int, list[str], list[str]]:
    owned_norm = {normalize_text(skill): skill for skill in owned}
    matched: list[str] = []
    missing: list[str] = []
    for skill in required:
        if normalize_text(skill) in owned_norm:
            matched.append(skill)
        else:
            missing.append(skill)
    score = round((len(matched) / max(len(required), 1)) * 100)
    return score, matched, missing
