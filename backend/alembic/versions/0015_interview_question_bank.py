"""Interview Question Bank v1.

Revision ID: 0015_interview_question_bank
Revises: 0014_product_analytics_v1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_interview_question_bank"
down_revision = "0014_product_analytics_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interview_question_bank",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("normalized_question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("category", sa.String(20), nullable=False, server_default="Other"),
        sa.Column("times_seen", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("seen_keys", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "normalized_question", name="uq_question_bank_user_normalized"),
    )
    op.create_index("ix_interview_question_bank_user_id", "interview_question_bank", ["user_id"])
    op.create_index("ix_interview_question_bank_category", "interview_question_bank", ["category"])
    op.create_index("ix_question_bank_user_sort", "interview_question_bank", ["user_id", "is_favorite", "times_seen", "updated_at"])


def downgrade():
    op.drop_table("interview_question_bank")
