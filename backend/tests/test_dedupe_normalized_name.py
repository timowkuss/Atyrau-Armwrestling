"""Дедуп спортсменов на сервере по нормализованному ФИО + дате рождения.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_dedupe_normalized_name -v

Раньше _find_existing_athlete сравнивал ФИО через ilike без учёта порядка
слов: «Пётр Петров» и «Петров Пётр» считались разными людьми, и один и
тот же спортсмен уезжал с десктопа на сервер второй раз под новым id
(дубли-карточки). После потери локальной id_map (переустановка, второй
компьютер) это давало каскад повреждений: несколько локальных карточек
на одного удалённого.

Теперь ФИО нормализуется (нижний регистр + слова по алфавиту), поэтому
порядок слов не важен. Дата рождения обязательна, чтобы не склеить
полных тёзок. Проверяем эндпоинт sync create_athlete напрямую.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models.athletes import Athlete
from app.schemas.sync import AthleteSyncCreate
from app.api.v1.sync.athletes import create_athlete as sync_create_athlete


class DedupeNormalizedNameTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def _count(self):
        return self.db.query(Athlete).count()

    def test_reversed_word_order_is_duplicate(self):
        first = sync_create_athlete(
            AthleteSyncCreate(
                full_name="Пётр Петров",
                birth_date="01.01.2000",
                gender="M",
            ),
            self.db, _=True,
        )
        self.assertEqual(first["status"], "created")
        second = sync_create_athlete(
            AthleteSyncCreate(
                full_name="Петров Пётр",
                birth_date="01.01.2000",
                gender="M",
            ),
            self.db, _=True,
        )
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["status"], "existing")
        self.assertEqual(self._count(), 1)

    def test_case_insensitive_is_duplicate(self):
        first = sync_create_athlete(
            AthleteSyncCreate(
                full_name="Иван Иванов",
                birth_date="05.05.1990",
            ),
            self.db, _=True,
        )
        second = sync_create_athlete(
            AthleteSyncCreate(
                full_name="иван иванов",
                birth_date="05.05.1990",
            ),
            self.db, _=True,
        )
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(self._count(), 1)

    def test_same_name_different_birth_date_not_duplicate(self):
        first = sync_create_athlete(
            AthleteSyncCreate(
                full_name="Пётр Петров",
                birth_date="01.01.2000",
            ),
            self.db, _=True,
        )
        second = sync_create_athlete(
            AthleteSyncCreate(
                full_name="Петров Пётр",
                birth_date="01.01.1990",
            ),
            self.db, _=True,
        )
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(self._count(), 2)

    def test_same_birth_date_different_person_not_duplicate(self):
        first = sync_create_athlete(
            AthleteSyncCreate(
                full_name="Иван Иванов",
                birth_date="01.01.1990",
            ),
            self.db, _=True,
        )
        second = sync_create_athlete(
            AthleteSyncCreate(
                full_name="Пётр Петров",
                birth_date="01.01.1990",
            ),
            self.db, _=True,
        )
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(self._count(), 2)

    def test_without_birth_date_no_dedupe(self):
        # Если даты рождения нет — не пытаемся сопоставлять по одному
        # имени: риск склеить разных людей. Раньше fallback в десктопе
        # (_find_or_create_athlete) создавал спортсмена БЕЗ birth_date,
        # и сервер плодил дубли — эта проверка фиксирует что так и будет,
        # но при обязательной дате (основной поток on_athlete_created)
        # дубль НЕ создаётся.
        first = sync_create_athlete(
            AthleteSyncCreate(full_name="Пётр Петров"),
            self.db, _=True,
        )
        second = sync_create_athlete(
            AthleteSyncCreate(full_name="Петров Пётр"),
            self.db, _=True,
        )
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(self._count(), 2)


if __name__ == "__main__":
    unittest.main()
