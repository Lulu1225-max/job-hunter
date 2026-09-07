from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_interview_question_metadata"
down_revision = "0003_candidate_matching_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interview_questions", sa.Column("source_platform", sa.String(length=120)))
    op.add_column("interview_questions", sa.Column("notes", sa.Text))


def downgrade() -> None:
    op.drop_column("interview_questions", "notes")
    op.drop_column("interview_questions", "source_platform")
