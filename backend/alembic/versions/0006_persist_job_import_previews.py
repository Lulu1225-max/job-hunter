"""Persist job import preview sessions.

Revision ID: 0006_persist_job_import_previews
Revises: 0005_resume_upload_fields
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_persist_job_import_previews"
down_revision = "0005_resume_upload_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_imports", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("job_imports", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_imports", sa.Column("status", sa.String(length=30), server_default="confirmed", nullable=False))
    op.add_column("job_imports", sa.Column("file_content", sa.LargeBinary(), nullable=True))
    op.add_column("job_imports", sa.Column("preview_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("ix_job_imports_user_status_expires", "job_imports", ["user_id", "status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_job_imports_user_status_expires", table_name="job_imports")
    for name in ("preview_payload", "file_content", "status", "expires_at", "created_at"):
        op.drop_column("job_imports", name)
