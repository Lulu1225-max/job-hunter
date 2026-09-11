from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import authenticate_supabase_password
from app.models.application import Application
from app.models.experience import Experience
from app.models.job import Job
from app.models.resume import Resume
from app.repositories.database import (
    applications_repo,
    ensure_user,
    experiences_repo,
    interview_questions_repo,
    interviews_repo,
    jobs_repo,
    profile_repo,
    resumes_repo,
)


PROFILE = {
    "display_name": "Alex Chen",
    "university": "海港城市大学",
    "degree": "计算机科学硕士",
    "major": "计算机科学",
    "specialisation": "人工智能方向",
    "graduation_year": 2027,
    "target_roles": ["AI 产品实习生", "产品经理实习生", "AI 产品管培生", "技术管培生"],
    "target_locations": ["悉尼", "上海", "深圳", "北京"],
    "preferred_job_types": ["实习", "校招", "internship", "graduate"],
    "technical_skills": ["Python", "SQL", "数据分析", "REST API", "LLM 应用", "Prompt Engineering", "RAG", "PostgreSQL", "Git", "基础 React"],
    "product_skills": ["产品分析", "需求定义", "用户研究", "实验设计", "产品指标", "AI 产品评估"],
    "soft_skills": ["沟通协作", "问题解决", "跨团队协作", "批判性思考", "利益相关方沟通", "汇报表达", "团队合作"],
    "tools": ["GitHub", "Figma", "Excel", "PostgreSQL", "Jupyter", "Codex"],
    "languages": ["中文", "英文"],
    "ai_response_language": "chinese",
}


RESUME_TEXT = """
Alex Chen - AI 产品方向简历

教育背景
海港城市大学，计算机科学硕士，人工智能方向，2026-2027
商业分析学士，2021-2025

实习经历
Nova AI Labs，AI 产品实习生，2026
参与 AI 文档助手产品优化，结合用户反馈整理高频问题与 bad case；与算法、开发和设计协作，定义 AI 输出质量评估维度；参与 Prompt 和交互流程优化，推动产品体验改进；将用户问题转化为产品需求，并协助推进需求落地；参与功能评审和效果复盘，输出改进建议。

BrightDrive Technology，产品实习生，2025
分析用户搜索行为和反馈，识别筛选与推荐流程中的主要问题；使用 Python 和 SQL 分析用户行为数据；参与推荐与筛选逻辑优化方案设计；协同设计和研发推动方案验证；参与定义功能上线后的核心评估指标。

项目经历
Career Copilot：AI 求职工作台，连接 Job Discovery、Resume Match、Application Tracking、Experience Retrieval 和 Interview Preparation。技术栈：Next.js、FastAPI、PostgreSQL、Python、LLM API、REST API。
校园餐食助手：面向学生的决策工具，根据偏好、类别、准备时间和历史记录推荐做饭选择。技术栈：Python、JSON、CLI。

技能
技术：Python、SQL、PostgreSQL、REST API、LLM 应用、RAG、Git。
产品：产品分析、用户研究、实验设计、产品指标、AI 产品评估。
通用能力：沟通协作、问题解决、跨团队协作。
""".strip()


RESUME = {
    "name": "Alex Chen - AI 产品方向简历",
    "file_url": "/demo/alex-chen-ai-product-resume.pdf",
    "extracted_text": RESUME_TEXT,
    "structured_content": {
        "education": [
            {"school": "海港城市大学", "degree": "计算机科学硕士", "specialisation": "人工智能方向", "period": "2026-2027"},
            {"degree": "商业分析学士", "period": "2021-2025"},
        ],
        "experience": [
            {"company": "Nova AI Labs", "role": "AI 产品实习生", "year": "2026"},
            {"company": "BrightDrive Technology", "role": "产品实习生", "year": "2025"},
        ],
        "projects": [
            {"name": "Career Copilot", "description": "AI 求职工作台，连接职位发现、简历匹配、申请追踪、经历检索和面试准备。", "technologies": ["Next.js", "FastAPI", "PostgreSQL", "Python", "LLM API", "REST API"]},
            {"name": "校园餐食助手", "description": "面向学生的做饭决策工具。", "technologies": ["Python", "JSON", "CLI"]},
        ],
        "technical_skills": ["Python", "SQL", "PostgreSQL", "REST API", "LLM 应用", "RAG", "Git"],
        "product_skills": ["产品分析", "用户研究", "实验设计", "产品指标", "AI 产品评估"],
        "soft_skills": ["沟通协作", "问题解决", "跨团队协作"],
        "tools": ["GitHub", "Figma", "Excel", "PostgreSQL", "Jupyter", "Codex"],
        "languages": ["中文", "英文"],
    },
    "is_default": True,
}


EXPERIENCES = [
    {"title": "AI 文档助手产品优化", "type": "internship", "description": "基于用户反馈和 bad case 推进 AI 文档助手体验优化。", "situation": "用户反馈 AI 输出不稳定，且部分结果缺乏可解释性。", "task": "定位主要问题，并提出可量化的改进方案。", "action": "整理用户反馈和 bad case，与研发共同定义评测维度，并参与 Prompt 和流程优化。", "result": "建立了一套结构化评测流程，并推动若干体验问题进入优化优先级。", "skills": ["产品分析", "LLM 评测", "沟通协作", "问题解决", "跨团队协作"], "technologies": ["LLM 应用", "Prompt Engineering"]},
    {"title": "搜索与推荐流程优化", "type": "internship", "description": "使用 Python 和 SQL 分析搜索、筛选和推荐链路中的问题。", "situation": "用户很难找到相关内容，筛选与搜索逻辑偏僵硬。", "task": "定位问题来源，并提出可验证的产品方案。", "action": "分析用户查询和行为数据，识别失败模式，并与研发讨论筛选逻辑调整。", "result": "输出了基于用户行为数据的产品优化方案。", "skills": ["数据分析", "SQL", "产品分析", "用户研究"], "technologies": ["Python", "SQL"]},
    {"title": "Career Copilot 项目", "type": "project", "description": "设计 AI 求职工作台，连接职位发现、简历匹配和面试准备。", "situation": "学生求职时需要在多个工具之间切换，信息和准备过程比较割裂。", "task": "设计一个统一的 AI 求职工作台。", "action": "设计核心流程、产品模块、数据库结构、API 架构和 AI 辅助功能。", "result": "完成了可运行 MVP，串联职位发现、简历匹配、申请追踪和面试准备。", "skills": ["产品设计", "AI 应用", "API 设计", "全栈开发", "问题解决"], "technologies": ["Next.js", "FastAPI", "PostgreSQL", "Python"]},
    {"title": "团队产品设计项目", "type": "coursework", "description": "在有限周期内协调需求和优先级，完成课程 MVP。", "situation": "课程团队需要在较短时间内设计并交付一个数字服务。", "task": "协调范围、统一优先级，并推动团队按计划交付。", "action": "收集需求、拆分功能优先级、协调分歧，并跟进交付节奏。", "result": "按期完成约定的 MVP 范围，并沉淀了需求取舍经验。", "skills": ["沟通协作", "团队合作", "利益相关方管理", "优先级判断"], "technologies": ["Figma"]},
    {"title": "未达预期的产品实验复盘", "type": "project", "description": "复盘一次效果不及预期的产品实验，重新设计分层和验证方案。", "situation": "一次产品改动预期能提升参与度，但上线后的初步结果弱于预期。", "task": "分析结果偏差原因，并调整实验设计。", "action": "回看原始假设和用户行为，发现分层假设有误，并重新设计实验方案。", "result": "形成了更合理的实验设计，并记录了后续产品决策的复盘结论。", "skills": ["复盘", "批判性思考", "实验设计", "数据分析"], "technologies": ["SQL", "产品指标"]},
]


JOBS = [
    {"company": "腾讯", "role": "AI 产品经理实习生", "location": "深圳", "job_url": "https://example.com/jobs/tencent-ai-product-manager-intern", "description": "参与 AI 产品需求分析、LLM 输出质量评估、产品指标分析和用户研究，与研发、算法、设计和运营协作，提升微信小程序工具类产品的留存与使用体验。", "industry": "互联网 / AI 产品", "job_type": "internship", "deadline": "2026-09-30", "technical_skills": ["Python", "SQL", "LLM 应用"], "product_skills": ["AI 产品评估", "产品分析", "产品指标", "用户研究", "实验设计"], "soft_skills": ["沟通协作", "跨团队协作"], "required_skills": ["AI 产品评估", "LLM 应用", "产品分析", "沟通协作", "实验设计", "产品指标"], "education_requirements": ["计算机科学", "人工智能"], "source": "seed_demo"},
    {"company": "TechNova", "role": "技术管培生", "location": "悉尼", "job_url": "https://example.com/jobs/technova-technology-graduate-program", "description": "校招轮岗项目，覆盖数据、产品和平台团队。候选人需要使用 SQL、Python、产品指标、API 理解和跨团队沟通能力支持产品与技术交付。", "industry": "科技", "job_type": "graduate", "deadline": "2026-10-20", "technical_skills": ["Python", "SQL", "REST API"], "product_skills": ["产品指标", "产品分析"], "soft_skills": ["利益相关方沟通", "团队合作"], "required_skills": ["Python", "SQL", "REST API", "产品指标", "利益相关方沟通"], "education_requirements": ["计算机科学"], "source": "seed_demo"},
    {"company": "Manual Real Job", "role": "后端开发实习生", "location": "悉尼", "job_url": "https://example.com/jobs/manual-real-backend-intern", "description": "后端实习岗位，重点关注系统设计、云基础设施、生产级后端服务、Docker、API 稳定性和后端框架深度。", "industry": "软件基础设施", "job_type": "internship", "deadline": "2026-11-01", "technical_skills": ["Python", "Docker", "云基础设施", "系统设计"], "product_skills": [], "soft_skills": ["问题解决"], "required_skills": ["Python", "Docker", "系统设计", "云基础设施", "生产级后端经验"], "education_requirements": ["计算机科学"], "source": "seed_demo"},
]


APPLICATIONS = [
    {"company": "Atlassian", "role": "软件工程实习生", "location": "悉尼", "job_url": "https://example.com/jobs/atlassian-software-engineer-intern", "salary": "AUD 45/hour", "application_date": "2026-08-12", "deadline": "2026-09-30", "status": "applied", "notes": "已通过校招系统提交简历和成绩单。", "source": "seed_demo"},
    {"company": "Canva", "role": "前端工程实习生", "location": "悉尼", "job_url": "https://example.com/jobs/canva-frontend-engineer-intern", "salary": "实习薪资面议", "application_date": "2026-08-18", "deadline": "2026-10-05", "status": "oa", "notes": "已收到在线测评邀请，重点准备 JavaScript 和产品思维题。", "source": "seed_demo"},
    {"company": "腾讯", "role": "AI 产品经理实习生", "location": "深圳", "job_url": "https://example.com/jobs/tencent-ai-product-manager-intern", "salary": "实习补贴", "application_date": "2026-08-20", "deadline": "2026-09-30", "status": "interview", "notes": "一面准备中，重点准备 AI 产品、用户留存和产品复盘。", "source": "seed_demo"},
    {"company": "Microsoft", "role": "软件工程管培生", "location": "墨尔本", "job_url": "https://example.com/jobs/microsoft-graduate-software-engineer", "salary": "校招薪资待确认", "application_date": "2026-07-29", "deadline": "2026-09-20", "status": "offer", "notes": "已收到口头 Offer，等待正式合同。", "source": "seed_demo"},
    {"company": "Amazon", "role": "软件开发实习生", "location": "悉尼", "job_url": "https://example.com/jobs/amazon-sde-intern", "salary": "实习薪资面议", "application_date": "2026-07-15", "deadline": "2026-08-30", "status": "rejected", "notes": "在线测评后被拒，保留题型复盘用于后续准备。", "source": "seed_demo"},
]


PUBLIC_QUESTIONS = [
    ("自我介绍", "Self Introduction"),
    ("你之前做的项目里，哪件事最能体现你的产品能力？说一下完整的过程。", "Product Experience"),
    ("你做的那个需求，当时你是怎么说服开发/设计接受你的方案的？中间有过什么分歧，怎么解决的？", "Cross-functional Collaboration"),
    ("给你一个业务场景：如何提升微信小程序某工具类产品的用户留存？你会怎么拆解和落地？", "Product Case"),
    ("之前你说你分析过某个产品，那你觉得它现在最大的短板是什么？如果让你接手，你会怎么改？", "Product Analysis"),
    ("如果你的方案被 leader 直接否定，而且没有给明确理由，你会怎么做？", "Stakeholder / Conflict Management"),
    ("你做过的产品相关的事里，有哪次结果和你的预期不一样？你事后复盘过吗？", "Reflection"),
    ("你怎么看待产品经理和运营、开发的关系？", "Role Understanding"),
    ("为什么选择腾讯？你觉得腾讯的产品和其他大厂的产品，在逻辑上有什么不一样？", "Company Motivation"),
    ("你未来想做什么方向的产品？为什么？", "Career Motivation"),
    ("反问环节", "Candidate Questions"),
]


AI_JD_QUESTIONS = [
    ("如果要评估一个 AI 产品功能是否成功，你会看哪些指标？为什么？", "Product Metrics"),
    ("面对一个 LLM 用户侧功能，你会如何定义质量指标和业务指标？", "AI Product Understanding"),
    ("如果模型质量和用户体验之间出现取舍，你会怎么判断优先级？", "Product Case"),
]


def main() -> None:
    demo_user_id, demo_email = get_demo_user_identity()
    db = SessionLocal()
    try:
        seed_demo_state(db, demo_user_id, demo_email)
        db.commit()
    finally:
        db.close()


def seed_demo_state(db, demo_user_id: UUID, demo_email: str | None) -> None:
    """Restore canonical records without resolving credentials or owning the transaction."""
    ensure_user(db, demo_user_id, email=demo_email, display_name=PROFILE["display_name"])
    profile_repo.upsert(db, demo_user_id, PROFILE)
    seed_resume(db, demo_user_id)
    seed_experiences(db, demo_user_id)
    jobs = seed_jobs(db, demo_user_id)
    seed_applications_and_interview(db, demo_user_id, jobs["腾讯"]["id"])


def get_demo_user_identity() -> tuple[UUID, str | None]:
    if not settings.demo_user_email or not settings.demo_user_password:
        raise RuntimeError("DEMO_USER_EMAIL and DEMO_USER_PASSWORD must be configured for demo seeding")
    session = authenticate_supabase_password(settings.demo_user_email, settings.demo_user_password)
    user = session["user"]
    return UUID(str(user["id"])), user.get("email")


def seed_resume(db, demo_user_id: UUID) -> None:
    db.execute(delete(Resume).where(Resume.user_id == demo_user_id, Resume.name.in_(["Persisted Resume", "Alex Chen - AI & Product Resume"])))
    existing = db.scalar(select(Resume).where(Resume.user_id == demo_user_id, Resume.name == RESUME["name"]))
    if existing:
        resumes_repo.update(db, demo_user_id, existing.id, RESUME)
    else:
        resumes_repo.create(db, demo_user_id, RESUME)


def seed_experiences(db, demo_user_id: UUID) -> None:
    db.execute(
        delete(Experience).where(
            Experience.user_id == demo_user_id,
            Experience.title.in_(
                [
                    "Database Import Project",
                    "AI Document Assistant Improvement",
                    "Search and Recommendation Improvement",
                    "Career Copilot Project",
                    "Team Product Design Project",
                    "Product Experiment That Missed Expectations",
                ]
            ),
        )
    )
    for item in EXPERIENCES:
        existing = db.scalar(select(Experience).where(Experience.user_id == demo_user_id, Experience.title == item["title"]))
        if existing:
            experiences_repo.update(db, demo_user_id, existing.id, item)
        else:
            experiences_repo.create(db, demo_user_id, item)


def seed_jobs(db, demo_user_id: UUID) -> dict[str, dict]:
    wanted = {(item["company"], item["role"]) for item in JOBS}
    stale = db.scalars(select(Job).where(Job.user_id == demo_user_id, Job.source == "seed_demo")).all()
    for row in stale:
        if (row.company, row.role) not in wanted:
            db.delete(row)
    db.execute(
        delete(Job).where(
            Job.user_id == demo_user_id,
            Job.source == "manual",
            Job.company == "Manual Real Job",
        )
    )
    seeded = {}
    for item in JOBS:
        job, _ = jobs_repo.upsert(db, demo_user_id, item)
        seeded[item["company"]] = job
    return seeded


def seed_applications_and_interview(db, demo_user_id: UUID, tencent_job_id: str) -> None:
    wanted = {(item["company"], item["role"]) for item in APPLICATIONS}
    stale = db.scalars(
        select(Application).where(
            Application.user_id == demo_user_id,
            Application.source == "seed_demo",
        )
    ).all()
    for row in stale:
        if (row.company, row.role) not in wanted:
            db.delete(row)
    tencent_application_id: UUID | None = None
    for item in APPLICATIONS:
        payload = {**item}
        if item["company"] == "腾讯":
            payload["job_id"] = tencent_job_id
        application = applications_repo.upsert_seed(db, demo_user_id, payload)
        if item["company"] == "腾讯":
            tencent_application_id = UUID(application["id"])
    if not tencent_application_id:
        return
    interview = interviews_repo.upsert_seed(
        db,
        tencent_application_id,
        {
            "round": "first_round",
            "interview_type": "product",
            "scheduled_at": datetime(2026, 9, 8, 10, 0),
            "status": "completed",
            "outcome": "passed",
            "difficulty": 4,
            "confidence": 3,
            "notes": "Demo 用户记录的一次模拟产品面试复盘。",
            "interviewer_notes": "重点追问了需求优先级与跨团队协作。",
            "went_well": "能够用真实项目说明需求梳理过程。",
            "to_improve": "回答结果时可以更清楚地区分事实与后续设想。",
        },
    )
    seed_questions(db, demo_user_id, tencent_application_id, interview.id)


def seed_questions(db, demo_user_id: UUID, application_id: UUID, interview_id: UUID) -> None:
    interview_questions_repo.upsert_seed(db,demo_user_id,{"interview_id":interview_id,"application_id":application_id,"company":"腾讯","role":"AI 产品经理实习生","question":"请讲一次你处理冲突需求并推动团队达成一致的经历。","category":"Conflict / collaboration","source":"actual_interview","notes":"Demo 用户自己的面试记录。"})
    for question, category in PUBLIC_QUESTIONS:
        interview_questions_repo.upsert_seed(
            db,
            demo_user_id,
            {
                "interview_id": interview_id,
                "application_id": application_id,
                "company": "腾讯",
                "role": "AI 产品经理实习生",
                "question": question,
                "category": category,
                "source": "public_research",
                "source_platform": "Nowcoder",
                "source_url": "https://www.nowcoder.com/feed/main/detail/bb14368c34ab4eefb2447f23866d732e?sourceSSR=search",
                "notes": "用户提供的公开面经题目，用于 demo 和参考。",
            },
        )
    for question, category in AI_JD_QUESTIONS:
        interview_questions_repo.upsert_seed(
            db,
            demo_user_id,
            {
                "interview_id": interview_id,
                "application_id": application_id,
                "company": "腾讯",
                "role": "AI 产品经理实习生",
                "question": question,
                "category": category,
                "source": "ai_generated",
                "source_platform": "Job Hunter",
                "notes": "根据持久化的腾讯 JD 生成。",
            },
        )


if __name__ == "__main__":
    main()
