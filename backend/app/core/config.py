from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "JobPilot"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://127.0.0.1:54329/jobhunter"
    frontend_origin: str = "http://127.0.0.1:3001"
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: str | None = None
    supabase_resume_bucket: str = "resumes"
    supabase_jwt_secret: str | None = None
    supabase_jwt_audience: str = "authenticated"
    demo_user_email: str | None = None
    demo_user_password: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    resume_upload_max_bytes: int = 10 * 1024 * 1024


settings = Settings()
