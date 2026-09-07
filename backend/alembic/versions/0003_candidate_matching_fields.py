from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_candidate_matching_fields"
down_revision = "0002_location_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("career_profiles", sa.Column("product_skills", postgresql.JSONB, nullable=False, server_default="[]"))
    op.add_column("resumes", sa.Column("structured_content", postgresql.JSONB, nullable=False, server_default="{}"))
    op.add_column("jobs", sa.Column("product_skills", postgresql.JSONB, nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("required_skills", postgresql.JSONB, nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("education_requirements", postgresql.JSONB, nullable=False, server_default="[]"))
    op.alter_column("career_profiles", "product_skills", server_default=None)
    op.alter_column("resumes", "structured_content", server_default=None)
    op.alter_column("jobs", "product_skills", server_default=None)
    op.alter_column("jobs", "required_skills", server_default=None)
    op.alter_column("jobs", "education_requirements", server_default=None)


def downgrade() -> None:
    op.drop_column("jobs", "education_requirements")
    op.drop_column("jobs", "required_skills")
    op.drop_column("jobs", "product_skills")
    op.drop_column("resumes", "structured_content")
    op.drop_column("career_profiles", "product_skills")
