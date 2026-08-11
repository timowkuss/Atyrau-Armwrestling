"""Секреты: значения-заглушки и короткие JWT_SECRET должны отклоняться.

Запуск: python -m pytest tests/security -q
"""

import unittest

from app.core.config import Settings, _FORBIDDEN_PLACEHOLDERS


class ConfigSecretsTest(unittest.TestCase):
    def _ok_settings(self, **kw):
        return Settings(JWT_SECRET="s" * 48, DESKTOP_SYNC_TOKEN="t" * 48, **kw)

    def test_strong_secrets_accepted(self):
        s = self._ok_settings()
        self.assertEqual(s.JWT_SECRET, "s" * 48)

    def test_empty_secrets_rejected(self):
        with self.assertRaises(RuntimeError):
            Settings(JWT_SECRET="", DESKTOP_SYNC_TOKEN="t" * 48)
        with self.assertRaises(RuntimeError):
            Settings(JWT_SECRET="s" * 48, DESKTOP_SYNC_TOKEN="")

    def test_placeholder_jwt_rejected(self):
        # Любое значение из .env.example (опубликовано в репозитории) —
        # кто угодно может подделать суперадминский JWT.
        for placeholder in _FORBIDDEN_PLACEHOLDERS:
            with self.subTest(placeholder=placeholder):
                with self.assertRaises(RuntimeError):
                    Settings(
                        JWT_SECRET=placeholder, DESKTOP_SYNC_TOKEN="t" * 48
                    )

    def test_placeholder_sync_token_rejected(self):
        for placeholder in _FORBIDDEN_PLACEHOLDERS:
            with self.subTest(placeholder=placeholder):
                with self.assertRaises(RuntimeError):
                    Settings(
                        JWT_SECRET="s" * 48, DESKTOP_SYNC_TOKEN=placeholder
                    )

    def test_short_jwt_rejected(self):
        # Меньше 32 символов — брутфорс подписи HS256.
        with self.assertRaises(RuntimeError):
            Settings(JWT_SECRET="short-secret", DESKTOP_SYNC_TOKEN="t" * 48)

    def test_uppercase_placeholder_also_rejected(self):
        with self.assertRaises(RuntimeError):
            Settings(
                JWT_SECRET="CHANGE-ME-IN-PRODUCTION",
                DESKTOP_SYNC_TOKEN="t" * 48,
            )


if __name__ == "__main__":
    unittest.main()
