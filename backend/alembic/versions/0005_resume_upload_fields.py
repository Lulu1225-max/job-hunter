from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_resume_upload_fields"
down_revision = "0004_interview_question_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    empty_skills = '{"technical_skills":[],"product_skills":[],"soft_skills":[],"tools":[],"languages":[]}'
    op.add_column("resumes", sa.Column("file_type", sa.String(length=10), nullable=False, server_default="pdf"))
    op.add_column(
        "resumes",
        sa.Column("detected_skills", postgresql.JSONB, nullable=False, server_default=empty_skills),
    )
    op.alter_column("resumes", "file_type", server_default=None)
    op.alter_column("resumes", "detected_skills", server_default=None)


def downgrade() -> None:
    op.drop_column("resumes", "detected_skills")
    op.drop_column("resumes", "file_type")
