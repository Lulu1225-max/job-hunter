"""Make Deep Resume Match cache language-aware.

Revision ID: 0011_match_response_language
Revises: 0010_nullable_match_scores
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_match_response_language"
down_revision = "0010_nullable_match_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resume_analyses",
        sa.Column("response_language", sa.String(length=20), nullable=False, server_default="legacy"),
    )
    op.alter_column("resume_analyses", "response_language", server_default="chinese")


def downgrade() -> None:
    op.drop_column("resume_analyses", "response_language")
