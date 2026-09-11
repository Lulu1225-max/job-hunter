"""Allow unavailable Deep Resume Match components.

Revision ID: 0010_nullable_match_scores
Revises: 0009_discovery_match_cache
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_nullable_match_scores"
down_revision = "0009_discovery_match_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("resume_analyses", "keyword_score", existing_type=sa.Integer(), nullable=True)
    op.alter_column("resume_analyses", "experience_score", existing_type=sa.Integer(), nullable=True)
    op.alter_column("resume_analyses", "overall_score", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE resume_analyses SET keyword_score = 0 WHERE keyword_score IS NULL")
    op.execute("UPDATE resume_analyses SET experience_score = 0 WHERE experience_score IS NULL")
    op.execute("UPDATE resume_analyses SET overall_score = 0 WHERE overall_score IS NULL")
    op.alter_column("resume_analyses", "keyword_score", existing_type=sa.Integer(), nullable=False)
    op.alter_column("resume_analyses", "experience_score", existing_type=sa.Integer(), nullable=False)
    op.alter_column("resume_analyses", "overall_score", existing_type=sa.Integer(), nullable=False)
