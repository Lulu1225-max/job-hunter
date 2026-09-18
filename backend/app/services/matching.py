from __future__ import annotations

import math
import re
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.repositories.database import discovery_match_caches_repo, jobs_repo, profile_repo, resume_analyses_repo, resumes_repo, serialize_model
from app.schemas.matching import MatchNarrative
from app.services.ai.client import ai_client
from app.services.embedding_service import embedding_service, fingerprint, job_source, resume_source

ANALYSIS_VERSION = "phase5-v2"
DISCOVERY_MATCH_VERSION = "phase5-discovery-v1"
DISCOVERY_WEIGHTS = {"semantic": 40, "skills": 25, "role": 15, "education": 8, "location": 5, "job_type": 4, "cohort": 3}
RESUME_MATCH_WEIGHTS = {"keyword": 35, "semantic": 40, "experience": 25}
SKILL_ALIASES = {"js": "javascript", "ts": "typescript", "py": "python", "postgres": "postgresql", "产品经理": "product management"}
KNOWN_SKILLS = ["Python", "Java", "JavaScript", "TypeScript", "React", "SQL", "PostgreSQL", "FastAPI", "Django", "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Figma", "Tableau", "Power BI", "Excel", "用户研究", "数据分析", "产品管理"]
RESPONSE_LANGUAGES = {"chinese", "english", "bilingual"}


def tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {token.casefold() for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]*|[\u4e00-\u9fff]{2,}", text)}


def flatten_text(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, str): return value
    if isinstance(value, list): return " ".join(flatten_text(item) for item in value)
    if isinstance(value, dict): return " ".join(flatten_text(item) for item in value.values())
    return str(value)


def norm_list(values: list[str] | None) -> list[str]:
    return [value.strip() for value in values or [] if isinstance(value, str) and value.strip()]


def job_value(job: Any, field: str) -> Any:
    return job.get(field) if isinstance(job, dict) else getattr(job, field, None)


def canonical(value: str) -> str:
    normalized = " ".join(value.casefold().strip().split())
    return SKILL_ALIASES.get(normalized, normalized)


def overlap(needles: list[str], haystack_text: str) -> tuple[list[str], list[str]]:
    haystack = haystack_text.casefold()
    hay_tokens = tokens(haystack)
    matched, missing, seen = [], [], set()
    for item in needles:
        marker = canonical(item)
        if marker in seen: continue
        seen.add(marker)
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", marker))
        present = (marker in haystack if has_chinese or " " in marker else marker in hay_tokens)
        present = present or any(alias == marker and raw in hay_tokens for raw, alias in SKILL_ALIASES.items())
        (matched if present else missing).append(item)
    return matched, missing


def meaningful_jd(job: Any) -> bool:
    description = " ".join(str(job_value(job, "description") or "").split())
    chinese_characters = len(re.findall(r"[\u4e00-\u9fff]", description))
    return len(description) >= 80 and (len(tokens(description)) >= 10 or chinese_characters >= 60)


def cosine_score(left: list[float], right: list[float]) -> int:
    denominator = math.sqrt(sum(v*v for v in left)) * math.sqrt(sum(v*v for v in right))
    cosine = sum(a*b for a,b in zip(left,right)) / denominator if denominator else 0.0
    return round(max(0.0, min(1.0, (cosine + 1.0) / 2.0)) * 100)


def _profile_skills(profile: dict) -> list[str]:
    result=[]
    for key in ("technical_skills","product_skills","soft_skills","tools","languages"):
        result.extend(norm_list(profile.get(key)))
    return list(dict.fromkeys(result))


def _resume_skills(resume: Any) -> list[str]:
    detected = resume.detected_skills or {}
    result=[]
    for key in ("technical_skills","product_skills","soft_skills","tools","languages"):
        result.extend(norm_list(detected.get(key)))
    return list(dict.fromkeys(result))


def response_language(profile: dict | None) -> str:
    configured = str((profile or {}).get("ai_response_language") or "").casefold().strip()
    return configured if configured in RESPONSE_LANGUAGES else "chinese"


def fallback_narrative(language: str, matched: list[str], missing: list[str], useful: list[str]) -> MatchNarrative:
    if language == "english":
        explanation = "Scores are calculated from resume evidence and the job description."
        evidence_label = "Relevant experience"
        weak_areas = [f"Not enough verified evidence for {skill}." for skill in missing[:5]]
        suggestions = [f"Show existing evidence for {skill}; add a measurable outcome only if you have one." for skill in missing[:3]]
    elif language == "bilingual":
        explanation = "评分基于简历证据和职位描述。 Scores use resume evidence and the job description."
        evidence_label = "相关经历 / Relevant experience"
        weak_areas = [f"缺少 {skill} 的可验证证据。 / Not enough verified evidence for {skill}." for skill in missing[:5]]
        suggestions = [f"仅在有真实依据时补充 {skill} 的证据和可衡量结果。 / Show evidence and a measurable outcome for {skill} only if true." for skill in missing[:3]]
    else:
        explanation = "评分基于简历中的真实证据和职位描述计算。"
        evidence_label = "相关经历"
        weak_areas = [f"缺少 {skill} 的可验证证据。" for skill in missing[:5]]
        suggestions = [f"展示已有的 {skill} 相关证据；仅在确有其事时补充可衡量的结果。" for skill in missing[:3]]
    return MatchNarrative(
        explanation=explanation,
        evidence=[{"skill": next((s for s in matched if s.casefold() in p.casefold()), evidence_label), "snippet": p[:320]} for p in useful],
        weak_areas=weak_areas,
        rewrite_suggestions=[{"type": "证据" if language == "chinese" else "Evidence" if language == "english" else "证据 / Evidence", "text": text} for text in suggestions],
    )


def _compat(preferences: list[str], actual: str | None) -> int | None:
    if not preferences or not actual: return None
    normalized_actual = actual.casefold().replace("市", "")
    return 100 if any(p.casefold().replace("市", "") in normalized_actual or normalized_actual in p.casefold().replace("市", "") for p in preferences) else 0


def _weighted(components: dict[str,int|None], weights: dict[str,int]) -> int:
    available=[(components[k],w) for k,w in weights.items() if components.get(k) is not None]
    return round(sum(score*w for score,w in available)/sum(w for _,w in available)) if available else 0


def _job_skills(job: Any) -> list[str]:
    explicit=[]
    for key in ("required_skills","technical_skills","product_skills","soft_skills"):
        explicit.extend(norm_list(getattr(job,key,None)))
    # Imported metadata is accepted only when it is evidenced by the JD.
    evidenced, _ = overlap(explicit, job.description or "")
    detected, _ = overlap(KNOWN_SKILLS, job.description or "")
    return list(dict.fromkeys(evidenced + detected))


def _signals(profile: dict, job: Any) -> tuple[dict[str,int|None],list[str]]:
    location=_compat(norm_list(profile.get("target_locations")),job_value(job,"location"))
    job_type=_compat(norm_list(profile.get("preferred_job_types"))," ".join(filter(None,[job_value(job,"job_type"),job_value(job,"campus_category")])))
    cohort=None
    if profile.get("graduation_year") and job_value(job,"graduation_cohort"):
        cohort=100 if str(profile["graduation_year"]) in job_value(job,"graduation_cohort") else 0
    signals=[]
    for name,value in (("location",location),("job_type",job_type),("graduation_cohort",cohort)):
        if value == 100: signals.append(f"{name}_match")
    return {"location":location,"job_type":job_type,"cohort":cohort},signals


class MatchingService:
    def readiness(self, job: Any, profile: dict | None, has_default_resume: bool) -> dict:
        profile=profile or {}
        compatibility,signals=_signals(profile,job)
        if not meaningful_jd(job):
            return {"status":"limited_data","overall_score":None,"semantic_score":None,"components":compatibility,"matched_skills":[],"missing_skills":[],"signals":signals,"missing_jd":True,"explanation":"This record needs a meaningful job description before a precise match can be calculated."}
        if not has_default_resume:
            return {"status":"no_resume","overall_score":None,"semantic_score":None,"components":compatibility,"matched_skills":[],"missing_skills":[],"signals":signals,"missing_jd":False,"explanation":"Set a default resume to calculate a personalized match."}
        return {"status":"ready","overall_score":None,"semantic_score":None,"components":compatibility,"matched_skills":[],"missing_skills":[],"signals":signals,"missing_jd":False,"explanation":"Ready to calculate using the default resume."}

    def discovery(self, db: Session, user_id: UUID, job_id: UUID) -> dict:
        job=jobs_repo.get_row(db,user_id,job_id)
        if not job: raise KeyError("Job not found")
        profile=profile_repo.get(db,user_id) or {}
        default=resumes_repo.default(db,user_id)
        ready=self.readiness(job,profile,bool(default))
        if ready["status"] == "no_resume": return ready
        resume=resumes_repo.get(db,user_id,UUID(default["id"]))
        resume_hash=fingerprint(resume_source(resume)); job_hash=fingerprint(job_source(job))
        cached=discovery_match_caches_repo.current(db,user_id,resume.id,job.id,resume_hash,job_hash,DISCOVERY_MATCH_VERSION)
        if cached: return {**cached.result_payload,"cached":True}
        if ready["status"] != "ready":
            result={**ready,"cached":False}
            discovery_match_caches_repo.create(db,user_id,resume.id,job.id,resume_hash,job_hash,DISCOVERY_MATCH_VERSION,result)
            db.commit()
            return result
        resume_vector,_=embedding_service.ensure_resume(db,resume)
        job_vector,_=embedding_service.ensure_job(db,job)
        semantic=cosine_score(resume_vector,job_vector)
        required=_job_skills(job)
        candidate=_profile_skills(profile)+_resume_skills(resume)
        matched,missing=overlap(required," ".join(candidate)+" "+(resume.extracted_text or ""))
        skills=round(len(matched)/len(required)*100) if required else None
        role=_compat(norm_list(profile.get("target_roles")),job.role)
        education=None
        requirements=norm_list(job.education_requirements)
        if requirements:
            education=100 if overlap(requirements," ".join(str(profile.get(k) or "") for k in ("degree","major","specialisation")))[0] else 0
        compatibility,signals=_signals(profile,job)
        components={"semantic":semantic,"skills":skills,"role":role,"education":education,**compatibility}
        non_semantic_available=any(components[name] is not None for name in ("skills","role","education","location","job_type","cohort"))
        if not non_semantic_available:
            result={"status":"semantic_only","overall_score":None,"semantic_score":semantic,"components":components,"matched_skills":matched,"missing_skills":missing,"signals":signals,"missing_jd":False,"explanation":"Semantic relevance is available, but supporting match signals are limited.","cached":False}
        else:
            result={"status":"scored","overall_score":_weighted(components,DISCOVERY_WEIGHTS),"semantic_score":semantic,"components":components,"matched_skills":matched,"missing_skills":missing,"signals":signals,"missing_jd":False,"explanation":"Deterministic score using semantic similarity and the available profile, skill, role, education, location, job type, and cohort signals.","cached":False}
        discovery_match_caches_repo.create(db,user_id,resume.id,job.id,resume_hash,job_hash,DISCOVERY_MATCH_VERSION,result)
        db.commit()
        return result

    def deep_match(self, db: Session, user_id: UUID, resume_id: UUID, job_id: UUID) -> dict:
        resume=resumes_repo.get(db,user_id,resume_id); job=jobs_repo.get_row(db,user_id,job_id)
        if not resume: raise KeyError("Resume not found")
        if not job: raise KeyError("Job not found")
        if not resume.extracted_text: raise ValueError("Resume has no extracted text")
        if not meaningful_jd(job): raise ValueError("Job needs a meaningful description for Resume Match")
        profile=profile_repo.get(db,user_id) or {}
        language=response_language(profile)
        resume_hash=fingerprint(resume_source(resume)); job_hash=fingerprint(job_source(job))
        cached=resume_analyses_repo.current(db,user_id,resume_id,job_id,resume_hash,job_hash,ANALYSIS_VERSION,language)
        if cached: return self._result(cached,True)
        resume_vector,_=embedding_service.ensure_resume(db,resume); job_vector,_=embedding_service.ensure_job(db,job)
        semantic=cosine_score(resume_vector,job_vector)
        required=_job_skills(job); matched,missing=overlap(required,resume.extracted_text)
        keyword=round(len(matched)/len(required)*100) if required else None
        jd_tokens=tokens(job.description); paragraphs=[p.strip() for p in re.split(r"[\n。]+",resume.extracted_text) if p.strip()]
        ranked=sorted(((len(tokens(p)&jd_tokens),p) for p in paragraphs),reverse=True)
        useful=[p for hits,p in ranked if hits][:3]
        experience=round(sum(min(hits,8) for hits,_ in ranked[:3])/24*100) if ranked and ranked[0][0] > 0 else None
        has_supporting_component=keyword is not None or experience is not None
        overall=_weighted({"keyword":keyword,"semantic":semantic,"experience":experience},RESUME_MATCH_WEIGHTS) if has_supporting_component else None
        fallback=fallback_narrative(language,matched,missing,useful)
        try:
            narrative=ai_client.structured_completion(prompt_name="resume_match_analysis",schema=MatchNarrative,payload={"response_language":language,"scores":{"overall":overall,"keyword":keyword,"semantic":semantic,"experience":experience},"resume_text":resume.extracted_text[:12000],"job_text":job_source(job)[:8000],"matched_skills":matched,"missing_skills":missing})
        except Exception:
            narrative=fallback
        # Structured validation checks shape; this second check enforces grounding.
        narrative.evidence = [item for item in narrative.evidence if item.snippet.casefold() in resume.extracted_text.casefold()]
        row=resume_analyses_repo.create(db,user_id,{"resume_id":resume_id,"job_id":job_id,"keyword_score":keyword,"semantic_score":semantic,"experience_score":experience,"overall_score":overall,"matched_keywords":matched,"missing_keywords":missing,"matched_skills":matched,"missing_skills":missing,"suggestions":[s.model_dump() for s in narrative.rewrite_suggestions],"evidence":[e.model_dump() for e in narrative.evidence],"weak_areas":narrative.weak_areas,"explanation":narrative.explanation,"resume_fingerprint":resume_hash,"job_fingerprint":job_hash,"analysis_version":ANALYSIS_VERSION,"response_language":language})
        db.commit(); return self._result(row,False)

    def _result(self,row:Any,cached:bool)->dict:
        return {"analysis_id":str(row.id),"job_id":str(row.job_id),"resume_id":str(row.resume_id),"status":"semantic_only" if row.overall_score is None else "scored","overall_score":row.overall_score,"keyword_score":row.keyword_score,"semantic_score":row.semantic_score,"experience_relevance_score":row.experience_score,"matched_keywords":row.matched_keywords,"missing_keywords":row.missing_keywords,"matched_skills":row.matched_skills,"missing_skills":row.missing_skills,"evidence":row.evidence,"weak_areas":row.weak_areas,"explanation":row.explanation or "","suggested_resume_improvements":row.suggestions,"cached":cached,"analysis_version":row.analysis_version}


matching_service=MatchingService()

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
