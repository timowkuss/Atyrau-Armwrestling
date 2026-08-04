"""Универсальный компаратор (сортировка) рейтингов спортсменов, тренеров и клубов.

Единая точка, где задаются правила порядка мест в рейтингах. Логика
начисления рейтинга здесь НЕ затрагивается: модуль только сортирует уже
посчитанные значения и раздаёт места (см. ARCHITECTURE.md).

Правила (одинаковые для всех трёх сущностей):
  1) первичный критерий — рейтинг (по убыванию);
  2) если рейтинг равен — «медальные очки»:
     1 🥇 = 2 🥈 = 3 🥉  (6 / 3 / 2 очка);
  3) третичный критерий (по убыванию):
     - спортсмены: винрейт wins / (wins + losses);
     - тренеры: количество активных учеников;
     - клубы: количество активных спортсменов;
  4) спортсмены дополнительно: количество побед (по убыванию);
  5) дата регистрации — кто раньше зарегистрирован, тот выше;
  6) ID — последний технический критерий (по возрастанию), полностью
     исключает совпадение ключей и делает порядок детерминированным.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Iterable, TypeVar

# Вес медалей в «медальных очках»: 1 🥇 = 2 🥈 = 3 🥉.
GOLD_POINTS = 6
SILVER_POINTS = 3
BRONZE_POINTS = 2

Entry = TypeVar("Entry")
SortKey = Callable[[Entry], tuple[Any, ...]]


def medal_points(gold: int = 0, silver: int = 0, bronze: int = 0) -> int:
    """Медальные очки из количества золотых/серебряных/бронзовых медалей.

    >>> medal_points(1, 3, 5)   # 6 + 9 + 10
    25
    >>> medal_points(2, 0, 10)  # 12 + 0 + 20
    32
    """
    return (
        gold * GOLD_POINTS
        + silver * SILVER_POINTS
        + bronze * BRONZE_POINTS
    )


def winrate(wins: int = 0, losses: int = 0) -> float:
    """Винрейт: wins / (wins + losses). Без проведённых матчей — 0.0."""
    total = wins + losses
    if total <= 0:
        return 0.0
    return wins / total


def registered_ts(value: date | datetime | None) -> float:
    """Числовое представление даты регистрации для сортировки.

    None (дата неизвестна) трактуется как «самый поздний» — такие записи
    опускаются в конец. В sort_key используйте с минусом: «кто раньше — выше».
    """
    if value is None:
        return 0.0
    return value.timestamp()


def compute_rankings(
    entries: list[Entry],
    sort_key: SortKey,
    limit: int | None = None,
) -> list[Entry]:
    """Сортирует entries по sort_key (кортеж, по убыванию) и раздаёт места.

    - Сортировка стабильная: при полностью одинаковых ключах относительный
      порядок записей сохраняется.
    - Одинаковые ключи получают одинаковое место; следующая запись получает
      номер на единицу больше количества предыдущих записей
      (стандартное соревновательное ранжирование: 1, 2, 2, 4, ...).
      На практике ключи всегда уникальны: цепочка заканчивается ID.
    - В каждую запись записывается поле "position" с местом.

    sort_key должен возвращать кортеж числовых значений: (рейтинг,
    медальные очки, третичный критерий, [победы], -дата регистрации, -id).
    Чем больше значение — тем выше место (reverse=True). Для критериев,
    где выше тот, у кого значение меньше (дата регистрации, ID), элементы
    берутся с минусом.
    """
    ranked = sorted(entries, key=sort_key, reverse=True)

    position = 0
    prev_key: tuple[Any, ...] | None = None
    for index, entry in enumerate(ranked):
        key = sort_key(entry)
        if prev_key is None or key != prev_key:
            # Первая запись группы: место = число предыдущих записей + 1.
            position = index + 1
            prev_key = key
        entry["position"] = position

    if limit is not None:
        return ranked[:limit]
    return ranked
