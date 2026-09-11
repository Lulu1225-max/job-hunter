"""Add persisted Phase 5 embeddings and analysis metadata.

Revision ID: 0008_phase5_embeddings
Revises: 0007_china_campus_job_metadata
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0008_phase5_embeddings"
down_revision = "0007_china_campus_job_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("resumes", sa.Column("embedding", Vector(1536), nullable=True))
    op.add_column("resumes", sa.Column("embedding_fingerprint", sa.String(64), nullable=True))
    op.add_column("jobs", sa.Column("embedding", Vector(1536), nullable=True))
    op.add_column("jobs", sa.Column("embedding_fingerprint", sa.String(64), nullable=True))
    op.add_column("resume_analyses", sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("resume_analyses", sa.Column("weak_areas", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("resume_analyses", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column("resume_analyses", sa.Column("resume_fingerprint", sa.String(64), nullable=True))
    op.add_column("resume_analyses", sa.Column("job_fingerprint", sa.String(64), nullable=True))
    op.add_column("resume_analyses", sa.Column("analysis_version", sa.String(32), nullable=False, server_default="phase5-v1"))
    op.execute("UPDATE resume_analyses SET resume_fingerprint = 'legacy', job_fingerprint = 'legacy'")
    op.alter_column("resume_analyses", "resume_fingerprint", nullable=False)
    op.alter_column("resume_analyses", "job_fingerprint", nullable=False)


def downgrade() -> None:
    for column in ("analysis_version", "job_fingerprint", "resume_fingerprint", "explanation", "weak_areas", "evidence"):
        op.drop_column("resume_analyses", column)
    op.drop_column("jobs", "embedding_fingerprint")
    op.drop_column("jobs", "embedding")
    op.drop_column("resumes", "embedding_fingerprint")
    op.drop_column("resumes", "embedding")
