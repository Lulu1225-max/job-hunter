"""Add Phase 7 interview prep and review fields.

Revision ID: 0013_phase7_interviews
Revises: 0012_experience_memory
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="0013_phase7_interviews"
down_revision="0012_experience_memory"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("interviews",sa.Column("user_id",postgresql.UUID(as_uuid=True),nullable=True))
    op.execute("UPDATE interviews SET user_id = applications.user_id FROM applications WHERE interviews.application_id = applications.id")
    op.alter_column("interviews","user_id",nullable=False)
    op.create_foreign_key("fk_interviews_user","interviews","users",["user_id"],["id"],ondelete="CASCADE")
    op.alter_column("interviews","round",type_=sa.String(80),postgresql_using="round::text")
    for name in ("difficulty","confidence"): op.add_column("interviews",sa.Column(name,sa.Integer(),nullable=True))
    for name in ("interviewer_notes","went_well","to_improve"): op.add_column("interviews",sa.Column(name,sa.Text(),nullable=True))
    op.add_column("interviews",sa.Column("outcome",sa.String(20),nullable=False,server_default="pending"))
    op.add_column("interview_answers",sa.Column("user_id",postgresql.UUID(as_uuid=True),nullable=True))
    op.execute("UPDATE interview_answers SET user_id = interview_questions.user_id FROM interview_questions WHERE interview_answers.question_id = interview_questions.id")
    op.alter_column("interview_answers","user_id",nullable=False)
    op.create_foreign_key("fk_interview_answers_user","interview_answers","users",["user_id"],["id"],ondelete="CASCADE")
    op.add_column("interview_answers",sa.Column("response_language",sa.String(20),nullable=False,server_default="legacy"))
    op.add_column("interview_answers",sa.Column("feedback",postgresql.JSONB(),nullable=True))
    op.add_column("interview_answers",sa.Column("follow_up_questions",postgresql.JSONB(),nullable=False,server_default="[]"))
    for name in ("question_fingerprint","job_fingerprint"):
        op.add_column("interview_answers",sa.Column(name,sa.String(64),nullable=False,server_default="legacy"))
    op.add_column("interview_answers",sa.Column("experience_fingerprint",sa.String(64),nullable=True))
    op.add_column("interview_answers",sa.Column("answer_version",sa.String(32),nullable=False,server_default="legacy"))

def downgrade():
    for name in ("answer_version","experience_fingerprint","job_fingerprint","question_fingerprint","follow_up_questions","feedback","response_language"):
        op.drop_column("interview_answers",name)
    op.drop_constraint("fk_interview_answers_user","interview_answers",type_="foreignkey")
    op.drop_column("interview_answers","user_id")
    for name in ("outcome","to_improve","went_well","interviewer_notes","confidence","difficulty"):
        op.drop_column("interviews",name)
    op.alter_column("interviews","round",type_=sa.Integer(),postgresql_using="NULLIF(round,'')::integer")
    op.drop_constraint("fk_interviews_user","interviews",type_="foreignkey")
    op.drop_column("interviews","user_id")
