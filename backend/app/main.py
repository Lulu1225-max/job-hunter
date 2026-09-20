from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import analytics, applications, auth, debug, experiences, jobs, profile, resumes, interviews, question_bank

app = FastAPI(title="Job Hunter API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router, prefix="/api/v1/profile", tags=["profile"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(applications.router, prefix="/api/v1/applications", tags=["applications"])
app.include_router(resumes.router, prefix="/api/v1/resumes", tags=["resumes"])
app.include_router(experiences.router, prefix="/api/v1/experiences", tags=["experiences"])
app.include_router(interviews.router, prefix="/api/v1", tags=["interviews"])
app.include_router(question_bank.router, prefix="/api/v1/interview/question-bank", tags=["question-bank"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(debug.router, prefix="/api/v1/debug", tags=["debug"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}
