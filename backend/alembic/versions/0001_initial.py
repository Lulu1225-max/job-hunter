from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "career_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(length=200)),
        sa.Column("target_roles", postgresql.JSONB, nullable=False),
        sa.Column("target_locations", postgresql.JSONB, nullable=False),
        sa.Column("target_industries", postgresql.JSONB, nullable=False),
        sa.Column("preferred_job_types", postgresql.JSONB, nullable=False),
        sa.Column("university", sa.String(length=250)),
        sa.Column("degree", sa.String(length=250)),
        sa.Column("major", sa.String(length=250)),
        sa.Column("specialisation", sa.String(length=250)),
        sa.Column("graduation_year", sa.Integer),
        sa.Column("technical_skills", postgresql.JSONB, nullable=False),
        sa.Column("soft_skills", postgresql.JSONB, nullable=False),
        sa.Column("tools", postgresql.JSONB, nullable=False),
        sa.Column("languages", postgresql.JSONB, nullable=False),
        sa.Column("ai_response_language", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_career_profiles_user_id"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("external_id", sa.String(length=250)),
        sa.Column("company", sa.String(length=250), nullable=False),
        sa.Column("role", sa.String(length=300)),
        sa.Column("location", sa.String(length=500)),
        sa.Column("job_url", sa.Text),
        sa.Column("salary", sa.String(length=250)),
        sa.Column("description", sa.Text),
        sa.Column("industry", sa.String(length=250)),
        sa.Column("job_type", sa.String(length=80)),
        sa.Column("application_open_date", sa.Date),
        sa.Column("deadline", sa.Date),
        sa.Column("graduation_cohort", sa.String(length=120)),
        sa.Column("technical_skills", postgresql.JSONB, nullable=False),
        sa.Column("soft_skills", postgresql.JSONB, nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "source_hash", name="uq_jobs_user_source_hash"),
    )
    op.create_index("ix_jobs_company", "jobs", ["company"])
    op.create_index("ix_jobs_role", "jobs", ["role"])
    op.create_index("ix_jobs_location", "jobs", ["location"])
    op.create_index("ix_jobs_industry", "jobs", ["industry"])
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_deadline", "jobs", ["deadline"])
    op.create_index("ix_jobs_graduation_cohort", "jobs", ["graduation_cohort"])
    op.create_index("ix_jobs_source_hash", "jobs", ["source_hash"])
    op.create_table(
        "job_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("sheet_name", sa.String(length=250), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_rows", sa.Integer, nullable=False),
        sa.Column("created_count", sa.Integer, nullable=False),
        sa.Column("updated_count", sa.Integer, nullable=False),
        sa.Column("skipped_count", sa.Integer, nullable=False),
        sa.Column("invalid_count", sa.Integer, nullable=False),
    )
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("company", sa.String(length=250), nullable=False),
        sa.Column("role", sa.String(length=300)),
        sa.Column("location", sa.String(length=500)),
        sa.Column("job_url", sa.Text),
        sa.Column("salary", sa.String(length=250)),
        sa.Column("application_date", sa.Date),
        sa.Column("deadline", sa.Date),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("file_url", sa.Text, nullable=False),
        sa.Column("extracted_text", sa.Text),
        sa.Column("is_default", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "resume_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword_score", sa.Integer, nullable=False),
        sa.Column("semantic_score", sa.Integer, nullable=False),
        sa.Column("experience_score", sa.Integer, nullable=False),
        sa.Column("overall_score", sa.Integer, nullable=False),
        sa.Column("matched_keywords", postgresql.JSONB, nullable=False),
        sa.Column("missing_keywords", postgresql.JSONB, nullable=False),
        sa.Column("matched_skills", postgresql.JSONB, nullable=False),
        sa.Column("missing_skills", postgresql.JSONB, nullable=False),
        sa.Column("suggestions", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "experiences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("situation", sa.Text),
        sa.Column("task", sa.Text),
        sa.Column("action", sa.Text),
        sa.Column("result", sa.Text),
        sa.Column("skills", postgresql.JSONB, nullable=False),
        sa.Column("technologies", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "interviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round", sa.Integer),
        sa.Column("interview_type", sa.String(length=80)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "interview_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interviews.id", ondelete="SET NULL")),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="SET NULL")),
        sa.Column("company", sa.String(length=250)),
        sa.Column("role", sa.String(length=300)),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("difficulty", sa.Integer),
        sa.Column("user_answer", sa.Text),
        sa.Column("ai_feedback", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "interview_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("experience_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiences.id", ondelete="SET NULL")),
        sa.Column("answer_30s", sa.Text),
        sa.Column("answer_1min", sa.Text),
        sa.Column("answer_2min", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("interview_answers")
    op.drop_table("interview_questions")
    op.drop_table("interviews")
    op.drop_table("experiences")
    op.drop_table("resume_analyses")
    op.drop_table("resumes")
    op.drop_table("applications")
    op.drop_table("job_imports")
    op.drop_table("jobs")
    op.drop_table("career_profiles")
    op.drop_table("users")
