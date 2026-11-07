"""Enrolment requests (admin approval) and the single-administrator rule (additive only).

* new table: ``enrollment_requests``
* new partial unique index ``uq_single_admin`` on ``users(role) WHERE role = 'admin'``

Fails (rather than guessing) if the database already holds more than one administrator.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollment_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("note", sa.String(500)),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime()),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="request_status"),
    )
    op.create_index("ix_enrollment_requests_student_id", "enrollment_requests", ["student_id"])
    op.create_index("ix_enrollment_requests_course_id", "enrollment_requests", ["course_id"])
    op.create_index("ix_enrollment_requests_status", "enrollment_requests", ["status"])
    op.create_index("uq_single_admin", "users", ["role"], unique=True, sqlite_where=sa.text("role = 'admin'"))


def downgrade() -> None:
    op.drop_index("uq_single_admin", table_name="users")
    op.drop_table("enrollment_requests")
