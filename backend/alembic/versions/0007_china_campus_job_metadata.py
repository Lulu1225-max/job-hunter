"""Add China campus recruitment metadata to jobs.

Revision ID: 0007_china_campus_job_metadata
Revises: 0006_persist_job_import_previews
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_china_campus_job_metadata"
down_revision = "0006_persist_job_import_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("jobs", "application_open_date", new_column_name="application_start_date")
    op.add_column("jobs", sa.Column("campus_category", sa.String(length=120), nullable=True))
    op.add_column("jobs", sa.Column("referral_available", sa.Boolean(), nullable=True))
    op.add_column("jobs", sa.Column("company_type", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "company_type")
    op.drop_column("jobs", "referral_available")
    op.drop_column("jobs", "campus_category")
    op.alter_column("jobs", "application_start_date", new_column_name="application_open_date")
