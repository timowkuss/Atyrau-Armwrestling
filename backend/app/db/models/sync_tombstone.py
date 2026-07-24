from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SyncTombstone(Base):
    """Лог жёстких удалений для десктопа (см. GET /sync/athletes/changes).

    Обновления ловятся сравнением Athlete.updated_at с курсором клиента,
    а вот факт "эту запись вообще удалили" по обновлениям не поймать —
    строки после DELETE просто нет. Поэтому при каждом жёстком удалении
    сюда пишется запись, а pull-эндпоинт отдаёт id всех удалённых с
    deleted_at > since вместе с обычными обновлениями.
    """

    __tablename__ = "sync_tombstones"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
