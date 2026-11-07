"""Authentication, roles, recommendation history and course archiving (additive only).

* new tables: ``users``, ``auth_sessions``, ``recommendation_history``
* new column: ``courses.is_active`` (every existing course stays active)

No existing table is rebuilt and no existing row is modified or removed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), unique=True),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime()),
        sa.CheckConstraint("role IN ('admin', 'student')", name="user_role"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)

    op.create_table(
        "recommendation_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="SET NULL")),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("model_trained_at", sa.String(40)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_recommendation_history_student_id", "recommendation_history", ["student_id"])
    op.create_index("ix_recommendation_history_created_at", "recommendation_history", ["created_at"])


def downgrade() -> None:
    # Only the objects this revision created are removed; student/ML data is never touched.
    op.drop_table("recommendation_history")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_column("courses", "is_active")
