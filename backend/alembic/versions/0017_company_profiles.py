"""Add cached AI-generated company profiles.

Revision ID: 0017_company_profiles
Revises: 0016_application_job_description
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_company_profiles"
down_revision = "0016_application_job_description"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_name", sa.String(250), nullable=False),
        sa.Column("normalized_company_name", sa.String(250), nullable=False, unique=True),
        sa.Column("positioning", sa.Text(), nullable=False),
        sa.Column("business_lines", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("key_brands", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("key_products", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("customer_groups", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("strategic_focus", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("comparable_products", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("interview_notes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("generation_version", sa.String(40), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_company_profiles_normalized_company_name", "company_profiles", ["normalized_company_name"], unique=True)


def downgrade():
    op.drop_index("ix_company_profiles_normalized_company_name", table_name="company_profiles")
    op.drop_table("company_profiles")
