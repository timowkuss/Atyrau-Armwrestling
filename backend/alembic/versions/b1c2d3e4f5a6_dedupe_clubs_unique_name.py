"""Сливает дубли клубов по имени и защищает таблицу от повторных дублей.

Revision ID: b1c2d3e4f5a6
Revises: f0a1b2c3d4e5
Create Date: 2026-08-04 12:00:00.000000

Проблема (обнаружена 2026-08-04): в таблице clubs оказалось 83 записи
при 8 уникальных именах — 72 клуба «Алга» и ещё несколько дублей. Клубов
на сайте стало «очень много», хотя реально их 8. Причина — create_club
создаёт новую строку без проверки на существующее имя (повторные
отправки из десктопной офлайн-очереди / импорты).

Миграция:
  1. Для каждой группы клубов с одинаковым именем (без учёта регистра)
     оставляет ОДИН клуб (минимальный id — самый старый), переназначает
     на него привязки (athletes / coaches / club_rating_history /
     club_rankings) и сливает баллы рейтинга из club_rating / club_rankings.
  2. Создаёт уникальный индекс на lower(name) — чтобы новые дубли
     физически не могли появиться (защита на будущее).

Дубли удаляются БЕЗ tombstone-записей: десктоп сам дедуплицирует клубы по
имени (sync/pull_sync.py::_upsert_club) и на следующем полном pull просто
перепривяжет свою локальную клубную карточку к каноническому remote-id.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _merge_ratings(bind, canonical: int, dup: int) -> None:
    """Сливает баллы рейтинга дубля в канонический клуб (до удаления строки,
    иначе FK ON DELETE CASCADE сотрёт их вместе с дублем)."""
    row = bind.execute(
        text("SELECT rating FROM club_rating WHERE club_id = :d"), {"d": dup}
    ).fetchone()
    if row and row[0]:
        existing = bind.execute(
            text("SELECT rating FROM club_rating WHERE club_id = :c"), {"c": canonical}
        ).fetchone()
        if existing:
            bind.execute(
                text("UPDATE club_rating SET rating = rating + :r WHERE club_id = :c"),
                {"r": row[0], "c": canonical},
            )
        else:
            bind.execute(
                text("INSERT INTO club_rating (club_id, rating) VALUES (:c, :r)"),
                {"c": canonical, "r": row[0]},
            )
    crk = bind.execute(
        text("SELECT points, gold_count, silver_count, bronze_count FROM club_rankings WHERE club_id = :d"),
        {"d": dup},
    ).fetchone()
    if crk:
        for col in ("points", "gold_count", "silver_count", "bronze_count"):
            val = crk._mapping[col]
            if val:
                existing = bind.execute(
                    text(f"SELECT {col} FROM club_rankings WHERE club_id = :c"),
                    {"c": canonical},
                ).fetchone()
                if existing and existing[0]:
                    bind.execute(
                        text(f"UPDATE club_rankings SET {col} = {col} + :v WHERE club_id = :c"),
                        {"v": val, "c": canonical},
                    )
                else:
                    bind.execute(
                        text(f"UPDATE club_rankings SET {col} = :v WHERE club_id = :c"),
                        {"v": val, "c": canonical},
                    )


def _dedupe(bind) -> None:
    names = [
        r[0]
        for r in bind.execute(
            text("SELECT lower(name) FROM clubs GROUP BY lower(name) HAVING count(*) > 1")
        ).fetchall()
    ]
    for nm in names:
        ids = [
            r[0]
            for r in bind.execute(
                text("SELECT id FROM clubs WHERE lower(name) = :n ORDER BY id"), {"n": nm}
            ).fetchall()
        ]
        canonical = ids[0]
        for dup in ids[1:]:
            _merge_ratings(bind, canonical, dup)
            for table, col in (
                ("athletes", "club_id"),
                ("coaches", "club_id"),
                ("club_rating_history", "club_id"),
                ("club_rankings", "club_id"),
            ):
                bind.execute(
                    text(f"UPDATE {table} SET {col} = :c WHERE {col} = :d"),
                    {"c": canonical, "d": dup},
                )
            bind.execute(text("DELETE FROM clubs WHERE id = :d"), {"d": dup})


def upgrade() -> None:
    bind = op.get_bind()
    _dedupe(bind)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_clubs_name_lower ON clubs (lower(name))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_clubs_name_lower")
