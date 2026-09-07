from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_location_text"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("jobs", "location", existing_type=sa.String(length=500), type_=sa.Text, existing_nullable=True)
    op.alter_column("applications", "location", existing_type=sa.String(length=500), type_=sa.Text, existing_nullable=True)


def downgrade() -> None:
    op.alter_column("applications", "location", existing_type=sa.Text, type_=sa.String(length=500), existing_nullable=True)
    op.alter_column("jobs", "location", existing_type=sa.Text, type_=sa.String(length=500), existing_nullable=True)
