"""results: UNIQUE участник+категория и check place >= 0

Revision ID: a3b4c5d6e7f8
Revises: a7b8c9d0e1f2
Create Date: 2026-08-11

"""

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Сначала вычищаем возможные дубли из прошлых повторных синхронизаций
    # (оставляем самую старую запись), иначе UNIQUE не создастся.
    op.execute(
        """
        DELETE FROM results
        WHERE id NOT IN (
            SELECT MIN(id) FROM results
            GROUP BY competition_id, category_id, competition_participant_id
        )
        """
    )
    op.create_check_constraint(
        "ck_results_place_positive", "results", "place IS NULL OR place >= 0"
    )
    op.create_unique_constraint(
        "uq_results_participant_category",
        "results",
        ["competition_id", "category_id", "competition_participant_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_results_participant_category", "results", type_="unique")
    op.drop_constraint("ck_results_place_positive", "results", type_="check")
