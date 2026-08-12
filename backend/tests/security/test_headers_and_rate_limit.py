"""Заголовки безопасности, CORS, rate limit логина.

Запуск: python -m pytest tests/security -q
"""

import os
import time

os.environ.setdefault(
    "JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef"
)
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import unittest

from fastapi.testclient import TestClient

from app import main as app_main
from app.api.v1 import auth
from app.core.config import settings


class SecurityHeadersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_main.app)

    def test_security_headers_present(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(r.headers.get("x-frame-options"), "DENY")
        self.assertIn("Strict-Transport-Security", r.headers)
        self.assertIn("Referrer-Policy", r.headers)
        csp = r.headers.get("content-security-policy", "")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_cors_no_wildcard_origin(self):
        r = self.client.get(
            "/health",
            headers={"Origin": "https://evil-example.com"},
        )
        # Чужой Origin не получает CORS-заголовков вообще.
        self.assertNotIn("access-control-allow-origin", r.headers)

    def test_cors_allows_frontend_origin(self):
        r = self.client.get(
            "/health",
            headers={"Origin": "https://atyrau-armwrestling.vercel.app"},
        )
        self.assertEqual(
            r.headers.get("access-control-allow-origin"),
            "https://atyrau-armwrestling.vercel.app",
        )

    def test_cors_no_credentials(self):
        r = self.client.get(
            "/health",
            headers={"Origin": "https://atyrau-armwrestling.vercel.app"},
        )
        # allow_credentials=False — ответ без заголовка credentials.
        self.assertNotIn("access-control-allow-credentials", r.headers)


class LoginRateLimitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Логин ходит в БД через get_db приложения. Подменяем зависимость
        # на общий StaticPool-движок (иначе in-memory sqlite видит
        # "no such table" из потока приложения).
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db import models  # noqa: F401
        from app.db.base import Base
        from app.db.session import get_db

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        cls._Session = sessionmaker(bind=engine)

        def override_db():
            db = cls._Session()
            try:
                yield db
            finally:
                db.close()

        app_main.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app_main.app)

    def setUp(self):
        # Между тестами сбрасываем in-memory счётчики попыток.
        auth._login_attempts.clear()
        auth._username_attempts.clear()

    def test_rate_limit_per_ip(self):
        ip = "203.0.113.7"
        payload = {"username": "nobody", "password": "x"}
        headers = {"X-Forwarded-For": ip}
        last_status = None
        for _ in range(auth._LOGIN_RATE_LIMIT + 3):
            r = self.client.post("/api/v1/auth/login", json=payload, headers=headers)
            last_status = r.status_code
        self.assertEqual(last_status, 429)

    def test_rate_limit_per_username(self):
        # Перебор с разных IP одного логина тоже упирается в лимит.
        payload = {"username": "target-user", "password": "x"}
        for i in range(auth._USERNAME_RATE_LIMIT + 2):
            r = self.client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={"X-Forwarded-For": f"198.51.100.{i}"},
            )
            last_status = r.status_code
        self.assertEqual(last_status, 429)

    def test_bad_credentials_401_same_message(self):
        # Единый ответ и для несуществующего, и для неверного пароля —
        # без энумерации имён.
        r1 = self.client.post(
            "/api/v1/auth/login", json={"username": "ghost", "password": "x"}
        )
        self.assertEqual(r1.status_code, 401)
        self.assertEqual(r1.json()["detail"], "Неверный логин или пароль")


if __name__ == "__main__":
    unittest.main()
