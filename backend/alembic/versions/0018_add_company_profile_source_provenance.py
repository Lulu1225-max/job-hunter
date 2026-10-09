"""Add source provenance to cached company profiles.

Revision ID: 0018_profile_provenance
Revises: 0017_company_profiles
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_profile_provenance"
down_revision = "0017_company_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_profiles",
        sa.Column(
            "source_provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("company_profiles", "source_provenance")
