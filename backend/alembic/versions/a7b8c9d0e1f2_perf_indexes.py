"""performance indexes

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-08-11

Модель app/db/models/matches.py объявляет
idx_matches_category_hand / idx_matches_category_hand_status в
__table_args__, но ни одна из существующих миграций их фактически не
создавала (create_table в 4d67b54f7d58_initial_schema.py — без индексов).
То есть в реальной БД их сейчас нет, хотя код и комментарии предполагают,
что есть. Эта миграция чинит расхождение и заодно добавляет пару
очевидно недостающих индексов под частые фильтры (клуб спортсмена,
результаты турнира).
"""
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # matches: уже объявлены в модели, но никогда не были в реальной БД
    op.create_index(
        "idx_matches_category_hand", "matches", ["category_id", "hand"]
    )
    op.create_index(
        "idx_matches_category_hand_status",
        "matches",
        ["category_id", "hand", "status"],
    )
    # athletes.club_id — фильтруется в списках клуба, рейтингах,
    # проверке неактивности и т.д.
    op.create_index("idx_athletes_club_id", "athletes", ["club_id"])
    # results.competition_id — используется при пересчёте/выдаче
    # результатов турнира (см. app/services/results_engine.py)
    op.create_index(
        "idx_results_competition_category",
        "results",
        ["competition_id", "category_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_results_competition_category", table_name="results")
    op.drop_index("idx_athletes_club_id", table_name="athletes")
    op.drop_index("idx_matches_category_hand_status", table_name="matches")
    op.drop_index("idx_matches_category_hand", table_name="matches")
