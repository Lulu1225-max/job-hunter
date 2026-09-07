from __future__ import annotations


def calculate_resume_match(keyword_score: int, semantic_score: int, experience_score: int) -> int:
    return round(keyword_score * 0.4 + semantic_score * 0.4 + experience_score * 0.2)
