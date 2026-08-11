from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

_connect_args = {}
if settings.DATABASE_URL.startswith("postgres"):
    # client_encoding — аргумент только Postgres-драйверов
    # (psycopg2/psycopg); sqlite его не принимает.
    _connect_args["client_encoding"] = "utf8"

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: сессия БД на время одного запроса."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
