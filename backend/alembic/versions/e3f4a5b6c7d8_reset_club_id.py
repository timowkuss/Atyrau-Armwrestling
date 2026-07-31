"""reset athlete and coach club_id to NULL

Revision ID: e3f4a5b6c7d8
Revises: d1e2f3a4b5c6
Create Date: 2026-07-31 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE athletes SET club_id = NULL WHERE club_id IS NOT NULL")
    op.execute("UPDATE coaches SET club_id = NULL WHERE club_id IS NOT NULL")


def downgrade() -> None:
    # Обратной операции нет — сброс клубов одноразовый, старые привязки
    # не восстанавливаются.
    pass
