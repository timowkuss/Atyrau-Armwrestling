import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401 — заполняет Base.metadata
from app.db.base import Base


@pytest.fixture()
def db_session():
    """Свежая in-memory SQLite база на каждый тест — быстро, изолированно,
    без внешних зависимостей (в проде — Postgres, но модели не используют
    ничего postgres-специфичного, так что для юнит-тестов бизнес-логики
    sqlite вполне достаточно)."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
