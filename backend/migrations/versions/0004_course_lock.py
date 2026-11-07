"""Course locking (additive only).

* new column ``courses.is_locked`` - every existing course stays LOCKED (admin approval required), which is how
  the system behaved before this revision; the administrator can unlock courses afterwards.

No row is modified or removed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("is_locked")
