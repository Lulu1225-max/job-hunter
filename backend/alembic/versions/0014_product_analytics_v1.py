"""Product Analytics v1 events.

Revision ID: 0014_product_analytics_v1
Revises: 0013_phase7_interviews
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_product_analytics_v1"
down_revision = "0013_phase7_interviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_name", sa.String(80), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="SET NULL")),
        sa.Column("experience_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiences.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16)),
        sa.Column("error_type", sa.String(80)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for name in ("user_id", "event_name", "created_at"):
        op.create_index(f"ix_analytics_events_{name}", "analytics_events", [name])
    op.create_index("ix_analytics_events_user_created", "analytics_events", ["user_id", "created_at"])


def downgrade():
    op.drop_table("analytics_events")
