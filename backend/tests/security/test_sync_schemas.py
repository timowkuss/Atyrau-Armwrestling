"""Sync-схемы: подмена победителя, статусы/руки вне словаря, лишние поля.

Запуск: python -m pytest tests/security -q
"""

import unittest

from pydantic import ValidationError

from app.schemas.sync import MatchSyncBatchCreate, MatchSyncCreate, MatchSyncUpdate


class SyncSchemasTest(unittest.TestCase):
    def _match(self, **kw):
        base = {
            "category_id": 1,
            "p1_id": 10,
            "p2_id": 20,
            "winner_id": None,
        }
        base.update(kw)
        return MatchSyncCreate(**base)

    def test_valid_match_ok(self):
        m = self._match()
        self.assertEqual(m.status, "pending")
        self.assertEqual(m.hand, "Правая")

    def test_winner_must_be_p1_or_p2(self):
        # Победитель «назначается» из участников другой категории — 422.
        with self.assertRaises(ValidationError):
            self._match(winner_id=999)

    def test_bye_without_winner_ok(self):
        m = self._match(p2_id=None, winner_id=None, is_bye=True)
        self.assertIsNone(m.p2_id)

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValidationError):
            self._match(status="какой-то-мусор")

    def test_invalid_hand_rejected(self):
        with self.assertRaises(ValidationError):
            self._match(hand="Левая_рука")

    def test_invalid_bracket_rejected(self):
        with self.assertRaises(ValidationError):
            self._match(bracket="quarterfinal")

    def test_negative_losses_rejected(self):
        with self.assertRaises(ValidationError):
            self._match(p1_losses=-1)

    def test_extra_field_rejected(self):
        # extra='forbid': десктоп, приславший неизвестное поле, получает
        # 422, а не молчаливую запись в обход схемы (mass assignment).
        with self.assertRaises(ValidationError):
            MatchSyncCreate(category_id=1, evil_field="x")

    def test_update_winner_without_participants_rejected(self):
        with self.assertRaises(ValidationError):
            MatchSyncUpdate(winner_id=5)

    def test_update_winner_not_in_pair_rejected(self):
        with self.assertRaises(ValidationError):
            MatchSyncUpdate(p1_id=1, p2_id=2, winner_id=3)

    def test_update_valid_ok(self):
        u = MatchSyncUpdate(p1_id=1, p2_id=2, winner_id=2)
        self.assertEqual(u.winner_id, 2)

    def test_batch_size_limited(self):
        # Защита от DoS гигантским телом запроса.
        too_many = [self._match() for _ in range(10001)]
        with self.assertRaises(ValidationError):
            MatchSyncBatchCreate(matches=too_many)


if __name__ == "__main__":
    unittest.main()
