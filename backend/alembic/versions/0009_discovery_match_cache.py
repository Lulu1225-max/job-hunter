"""Add persisted Discovery Match result cache.

Revision ID: 0009_discovery_match_cache
Revises: 0008_phase5_embeddings
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_discovery_match_cache"
down_revision = "0008_phase5_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_match_caches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_fingerprint", sa.String(64), nullable=False),
        sa.Column("job_fingerprint", sa.String(64), nullable=False),
        sa.Column("scoring_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "resume_id", "job_id", "resume_fingerprint", "job_fingerprint", "scoring_version", name="uq_discovery_match_cache_source_version"),
    )
    op.create_index("ix_discovery_match_caches_user_job", "discovery_match_caches", ["user_id", "job_id"])


def downgrade() -> None:
    op.drop_index("ix_discovery_match_caches_user_job", table_name="discovery_match_caches")
    op.drop_table("discovery_match_caches")
