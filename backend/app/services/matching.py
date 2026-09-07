from __future__ import annotations

import re
from typing import Any


def tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z+#.]*|[\u4e00-\u9fff]{2,}", text)}


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(flatten_text(item) for item in value.values())
    return str(value)


def norm_list(values: list[str] | None) -> list[str]:
    return [value.strip() for value in values or [] if isinstance(value, str) and value.strip()]


def overlap(needles: list[str], haystack_text: str) -> tuple[list[str], list[str]]:
    lower = haystack_text.lower()
    seen = set()
    matched = []
    for item in needles:
        marker = item.lower()
        if marker in lower and marker not in seen:
            matched.append(item)
            seen.add(marker)
    missing = []
    missing_seen = set()
    for item in needles:
        marker = item.lower()
        if item not in matched and marker not in missing_seen:
            missing.append(item)
            missing_seen.add(marker)
    return matched, missing


def analyse_job_match(profile: dict | None, resume: dict | None, job: dict) -> dict[str, Any]:
    profile = profile or {}
    resume_text = f"{resume.get('extracted_text') or ''} {flatten_text(resume.get('structured_content')) if resume else ''}"
    job_text = " ".join(
        [
            str(job.get("company") or ""),
            str(job.get("role") or ""),
            str(job.get("location") or ""),
            str(job.get("industry") or ""),
            str(job.get("job_type") or ""),
            str(job.get("description") or ""),
            flatten_text(job.get("required_skills")),
            flatten_text(job.get("technical_skills")),
            flatten_text(job.get("product_skills")),
            flatten_text(job.get("soft_skills")),
        ]
    )
    has_deep_data = bool(job.get("description") or job.get("required_skills") or job.get("product_skills"))

    candidate_skills = (
        norm_list(profile.get("technical_skills"))
        + norm_list(profile.get("product_skills"))
        + norm_list(profile.get("soft_skills"))
        + norm_list(profile.get("tools"))
    )
    required = (
        norm_list(job.get("required_skills"))
        + norm_list(job.get("technical_skills"))
        + norm_list(job.get("product_skills"))
        + norm_list(job.get("soft_skills"))
    )
    if not required and has_deep_data:
        required = [skill for skill in candidate_skills if skill.lower() in job_text.lower()]

    matched_skills, missing_skills = overlap(required, " ".join(candidate_skills) + " " + resume_text)
    role_matches, _ = overlap(norm_list(profile.get("target_roles")), f"{job.get('role') or ''} {job.get('description') or ''}")
    location_matches, _ = overlap(norm_list(profile.get("target_locations")), str(job.get("location") or ""))
    job_type_matches, _ = overlap(norm_list(profile.get("preferred_job_types")), str(job.get("job_type") or ""))
    education_matches, _ = overlap(
        [profile.get("degree"), profile.get("major"), profile.get("specialisation")],
        f"{flatten_text(job.get('education_requirements'))} {job_text}",
    )

    if not has_deep_data:
        return {
            "level": "limited",
            "label": "潜在匹配" if location_matches or job_type_matches else "匹配信息不足",
            "score": None,
            "confidence": "low",
            "matched_skills": [],
            "missing_skills": [],
            "location_match": location_matches,
            "job_type_match": job_type_matches,
            "education_match": education_matches,
            "reason": "由于当前职位缺少完整 JD，暂时无法进行详细技能匹配。补充职位描述后可重新计算岗位匹配度。",
        }

    skill_score = round((len(matched_skills) / max(len(required), 1)) * 100)
    job_token_set = tokens(job_text)
    role_score = 100 if role_matches else 45 if job_token_set & {"product", "ai", "data"} else 20
    location_score = 100 if location_matches else 40
    job_type_score = 100 if job_type_matches else 50
    education_score = 100 if education_matches else 65
    resume_score = round((len(tokens(job_text) & tokens(resume_text)) / max(len(tokens(job_text)), 1)) * 100)
    score = round(
        role_score * 0.24
        + skill_score * 0.28
        + location_score * 0.12
        + job_type_score * 0.08
        + education_score * 0.10
        + min(resume_score * 2, 100) * 0.18
    )
    return {
        "level": "scored",
        "label": f"{score}% 匹配",
        "score": score,
        "confidence": "high" if job.get("description") else "medium",
        "components": {
            "role_relevance": role_score,
            "skill_match": skill_score,
            "location_preference": location_score,
            "job_type": job_type_score,
            "education_relevance": education_score,
            "resume_relevance": min(resume_score * 2, 100),
        },
        "matched_skills": matched_skills[:10],
        "missing_skills": missing_skills[:8],
        "location_match": location_matches,
        "job_type_match": job_type_matches,
        "education_match": education_matches,
        "reason": "匹配度基于持久化职业档案、默认简历、职位描述、岗位要求、地点和招聘类型计算。",
    }


def analyse_resume_match(profile: dict | None, resume: dict, job: dict, experiences: list[dict]) -> dict[str, Any]:
    match = analyse_job_match(profile, resume, job)
    resume_text = f"{resume.get('extracted_text') or ''} {flatten_text(resume.get('structured_content'))}"
    job_terms = norm_list(job.get("required_skills")) + norm_list(job.get("product_skills")) + norm_list(job.get("technical_skills"))
    matched_keywords, missing_keywords = overlap(job_terms, resume_text)
    evidence = retrieve_experiences(job, experiences)[:3]
    experience_score = evidence[0]["score"] if evidence else 0
    keyword_score = round((len(matched_keywords) / max(len(job_terms), 1)) * 100) if job_terms else 0
    semantic_score = match.get("components", {}).get("resume_relevance", 0) if match.get("level") == "scored" else 0
    overall = round(keyword_score * 0.35 + semantic_score * 0.30 + experience_score * 0.35)
    return {
        "job_id": job["id"],
        "resume_id": resume["id"],
        "overall_score": overall,
        "keyword_score": keyword_score,
        "semantic_score": semantic_score,
        "experience_relevance_score": experience_score,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "matched_skills": match.get("matched_skills", []),
        "missing_skills": match.get("missing_skills", []),
        "strong_experience_evidence": evidence,
        "weak_areas": missing_keywords[:5],
        "suggested_resume_improvements": [
            {"type": "改写已有证据", "text": "把简历中已有的 AI 产品评估、产品指标和跨团队协作经历写得更具体，方便面试官快速看到匹配点。"},
            {"type": "缺少经历 / 证据", "text": "如果确实做过增长实验、A/B Testing 或大规模上线复盘，可以补充；如果没有，不要编造。"},
        ],
    }


def retrieve_experiences(target: dict, experiences: list[dict]) -> list[dict[str, Any]]:
    category = str(target.get("category") or "").lower()
    category_terms = {
        "product experience": "Career Copilot 产品设计 AI 应用 产品能力 端到端 产品思维",
        "cross-functional collaboration": "团队产品设计 利益相关方 分歧 沟通 研发 设计 协作 对齐",
        "stakeholder / conflict management": "团队产品设计 利益相关方 分歧 沟通 优先级 对齐",
        "reflection": "未达预期 产品实验 复盘 批判性思考 实验设计",
        "product case": "产品实验 搜索 推荐 用户留存 产品指标 实验设计",
        "product analysis": "搜索 推荐 产品分析 用户研究 SQL 数据分析",
        "product metrics": "产品实验 产品指标 LLM 评测 AI 产品评估",
        "ai product understanding": "AI 文档助手 LLM 评测 AI 应用 产品需求",
    }
    target_text = f"{flatten_text(target)} {category_terms.get(category, '')}"
    target_tokens = tokens(target_text)
    title_boosts = {
        "product experience": {"Career Copilot 项目": 22, "AI 文档助手产品优化": 12},
        "cross-functional collaboration": {"团队产品设计项目": 22, "AI 文档助手产品优化": 12},
        "stakeholder / conflict management": {"团队产品设计项目": 24},
        "reflection": {"未达预期的产品实验复盘": 24},
        "product case": {"未达预期的产品实验复盘": 16, "搜索与推荐流程优化": 14},
        "product analysis": {"搜索与推荐流程优化": 24},
        "product metrics": {"未达预期的产品实验复盘": 18, "AI 文档助手产品优化": 12},
        "ai product understanding": {"AI 文档助手产品优化": 18, "Career Copilot 项目": 12},
    }
    results = []
    for exp in experiences:
        exp_text = flatten_text(exp)
        shared = target_tokens & tokens(exp_text)
        skill_hits = [skill for skill in norm_list(exp.get("skills")) + norm_list(exp.get("technologies")) if skill.lower() in target_text.lower()]
        boost = title_boosts.get(category, {}).get(exp.get("title"), 0)
        score = min(98, 45 + len(shared) * 5 + len(skill_hits) * 8 + boost)
        reason = f"相关技能/证据：{', '.join(skill_hits[:5]) or '与题目有重合的产品经历和行为证据'}。"
        if boost:
            reason = f"非常适合回答「{target.get('category')}」类问题：{reason}"
        results.append(
            {
                "experience_id": exp["id"],
                "title": exp["title"],
                "score": score,
                "_boost": boost,
                "why": reason,
            }
        )
    ranked = sorted(results, key=lambda item: (item["score"], item["_boost"]), reverse=True)
    for item in ranked:
        item.pop("_boost", None)
    return ranked


def generate_answer(question: dict, experience: dict) -> dict[str, str]:
    situation = experience.get("situation") or experience.get("description") or "这个例子来自我经历库里保存的一段真实经历。"
    task = experience.get("task") or "我当时的任务是把问题讲清楚，并推动团队形成可执行方案。"
    action = experience.get("action") or "我先分析证据，再和相关同学或同事对齐，并提出可落地的方案。"
    result = experience.get("result") or "最后团队对问题和后续方向有了更清楚的判断。"
    compact = f"我会用「{experience['title']}」这个例子来回答。当时的背景是：{situation} 我的任务是：{task} 我主要做了几件事：{action} 最后的结果是：{result}"
    return {
        "answer_30s": compact[:520],
        "answer_1min": compact,
        "answer_2min": f"{compact} 如果展开到两分钟，我会再补充当时如何判断优先级、怎样和研发或设计沟通，以及这件事让我学到：产品判断不能只停留在想法上，要能落到用户问题、评估指标和可执行方案上。回答时只基于这段经历，不额外编造指标或结果。",
    }


def analyse_user_answer(answer: str, question: dict, experiences: list[dict]) -> dict[str, Any]:
    relevant = retrieve_experiences({"question": question.get("question"), "answer": answer}, experiences)[:2]
    has_star = all(word in answer.lower() for word in ["situation", "task", "action", "result"])
    return {
        "strengths": ["回答方向比较具体" if answer.strip() else "可以先从一个真实经历开始起草"],
        "weaknesses": [] if len(answer) > 120 else ["还需要补充更具体的经历证据。"],
        "missing_evidence": ["如果真实经历里有可观察结果、复盘结论或指标变化，可以补充；没有就不要硬编。"],
        "structure_feedback": "已经能看出 STAR 结构。" if has_star else "建议补清楚背景、任务、行动和结果四个层次，但表达上不用机械背模板。",
        "clarity_feedback": "开头可以更直接，先说你要用哪个例子，再连接到产品影响。",
        "star_feedback": "尽量围绕一段经历讲完整，不要把多个无关例子混在一起。",
        "potential_follow_up_questions": ["为什么选择这个指标？", "你会怎么验证这个假设？", "如果结果没有提升，你下一步会怎么做？"],
        "suggested_improved_version": generate_answer(question, relevant and next((exp for exp in experiences if exp["id"] == relevant[0]["experience_id"]), experiences[0])) if experiences else {},
    }
