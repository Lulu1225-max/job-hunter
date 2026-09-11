"""Add Phase 6 experience memory fields.

Revision ID: 0012_experience_memory
Revises: 0011_match_response_language
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0012_experience_memory"
down_revision = "0011_match_response_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiences", sa.Column("reflection", sa.Text(), nullable=True))
    op.add_column("experiences", sa.Column("embedding", Vector(1536), nullable=True))
    op.add_column("experiences", sa.Column("embedding_fingerprint", sa.String(64), nullable=True))
    op.execute("""UPDATE experiences SET type = CASE type
        WHEN '实习' THEN 'internship' WHEN 'work' THEN 'internship'
        WHEN '项目' THEN 'project' WHEN '课程' THEN 'coursework' WHEN 'education' THEN 'coursework'
        WHEN '领导力' THEN 'leadership' WHEN '志愿者' THEN 'volunteer' WHEN '竞赛' THEN 'competition'
        ELSE CASE WHEN type IN ('internship','project','coursework','leadership','volunteer','competition','other') THEN type ELSE 'other' END END""")


def downgrade() -> None:
    op.drop_column("experiences", "embedding_fingerprint")
    op.drop_column("experiences", "embedding")
    op.drop_column("experiences", "reflection")
