"""Эндпоинт /public/athletes/birthdays — именинники на сегодня и завтра.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_birthdays -v

Проверяет:
  - выборку по месяцу и дню (год не важен) для сегодня и завтра;
  - day_offset: 0 — сегодня, 1 — завтра;
  - turns_age — возраст, который исполняется;
  - скрытых спортсменов (is_hidden) и спортсменов без даты рождения не отдаёт.
"""
from __future__ import annotations

import os
import unittest
from datetime import date, timedelta

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401  (регистрирует все модели в Base.metadata)
from app.db.models.athletes import Athlete
from app.api.v1.public.athletes import upcoming_birthdays


def _birthday_in(year: int, base: date) -> date:
    """Дата рождения с тем же месяцем/днём, что у base, но в год year."""
    return date(year, base.month, base.day)


class BirthdayEndpointTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def _athlete(self, full_name, birth_date, is_hidden=False):
        a = Athlete(full_name=full_name, birth_date=birth_date, is_hidden=is_hidden)
        self.db.add(a)
        self.db.flush()
        return a

    def test_returns_today_and_tomorrow_birthdays(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)

        self._athlete("Сегодняшний", _birthday_in(1990, today))
        self._athlete("Завтрашний", _birthday_in(2001, tomorrow))
        # тот же месяц/день, но другой год — тоже именинник
        self._athlete("Совпадающий", _birthday_in(1985, today))
        # не именинник: другая дата
        self._athlete("Обычный", date(2000, 1, 1))
        # без даты рождения и скрытый — не должны попасть
        self._athlete("Без даты", None)
        self._athlete("Скрытый", _birthday_in(1995, today), is_hidden=True)
        self.db.commit()

        items = upcoming_birthdays(db=self.db)
        by_name = {i.full_name: i for i in items}

        self.assertEqual(len(items), 3)
        self.assertEqual(by_name["Сегодняшний"].day_offset, 0)
        self.assertEqual(by_name["Сегодняшний"].turns_age, today.year - 1990)
        self.assertEqual(by_name["Совпадающий"].day_offset, 0)
        self.assertEqual(by_name["Завтрашний"].day_offset, 1)
        self.assertEqual(by_name["Завтрашний"].turns_age, tomorrow.year - 2001)
        self.assertNotIn("Обычный", by_name)
        self.assertNotIn("Без даты", by_name)
        self.assertNotIn("Скрытый", by_name)

    def test_empty_when_no_birthdays(self):
        self._athlete("Обычный", date(2000, 1, 1))
        self.db.commit()
        items = upcoming_birthdays(db=self.db)
        self.assertEqual(items, [])

    def test_sorted_by_full_name(self):
        today = date.today()
        self._athlete("Борис", _birthday_in(1990, today))
        self._athlete("Анна", _birthday_in(1991, today))
        self.db.commit()
        items = upcoming_birthdays(db=self.db)
        self.assertEqual([i.full_name for i in items], ["Анна", "Борис"])


if __name__ == "__main__":
    unittest.main()
