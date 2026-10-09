"""Add an independent job description snapshot to applications.

Revision ID: 0016_application_job_description
Revises: 0015_interview_question_bank
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_application_job_description"
down_revision = "0015_interview_question_bank"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("job_description", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE applications AS application
        SET job_description = job.description
        FROM jobs AS job
        WHERE application.job_id = job.id
          AND application.job_description IS NULL
          AND job.description IS NOT NULL
        """
    )


def downgrade():
    op.drop_column("applications", "job_description")
