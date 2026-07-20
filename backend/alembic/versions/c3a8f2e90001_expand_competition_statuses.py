"""expand competition statuses: in_progress, completed

Revision ID: c3a8f2e90001
Revises: a2f4c9e17d33
Create Date: 2025-07-20
"""

from alembic import op

revision = "c3a8f2e90001"
down_revision = "a2f4c9e17d33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE competitions DROP CONSTRAINT ck_competitions_status")
    op.execute(
        "ALTER TABLE competitions ADD CONSTRAINT ck_competitions_status "
        "CHECK (status IN ('draft','published','in_progress','completed'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE competitions DROP CONSTRAINT ck_competitions_status")
    op.execute(
        "ALTER TABLE competitions ADD CONSTRAINT ck_competitions_status "
        "CHECK (status IN ('draft','published'))"
    )
