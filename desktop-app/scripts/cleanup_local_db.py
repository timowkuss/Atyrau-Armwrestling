"""Очистка локальной SQLite БД desktop-app (armwrestling.db).

Удаляет: спортсменов, тренеров, клубов, турниры + всё связанное
(категории, участники, матчи, рейтинги, генерации сеток).
Сохраняет справочные данные и структуру таблиц (схема не меняется).
Сбрасывает счётчики AUTOINCREMENT (id начнутся с 1).

Безопасно: работает в транзакции, при ошибке — rollback.
Перед запуском рекомендуется создать резервную копию (backup_manager или
просто скопировать armwrestling.db).
"""
import sqlite3
import sys

DB = r"armwrestling.db"

TABLES = [
    "matches",
    "participants",
    "weight_categories",
    "dvoeborie_overrides",
    "bracket_generations",
    "transfer_marks",
    "tournaments",
    "club_rating_history",
    "club_rating",
    "athletes",
    "coaches",
    "clubs",
]

SEQUENCES = [
    "tournaments", "weight_categories", "participants", "matches",
    "athletes", "coaches", "clubs", "club_rating", "club_rating_history",
]


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("BEGIN")

        def count(t):
            return conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]

        before = {t: count(t) for t in TABLES}
        for t in TABLES:
            conn.execute(f'DELETE FROM "{t}"')
            print(f"  DELETED {before[t]:6d} rows from {t}")

        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN (%s)"
            % ",".join("?" * len(SEQUENCES)),
            SEQUENCES,
        )
        print("\n  sqlite_sequence reset.")

        conn.commit()
        print("\nCOMMITTED.")
        print("\nRemaining (should be 0):")
        for t in TABLES:
            n = count(t)
            if n:
                print(f"  !! {t}: {n} left")
        return 0
    except Exception as e:
        conn.rollback()
        print("ROLLBACK:", e)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
