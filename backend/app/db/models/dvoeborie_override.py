from __future__ import annotations

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DvoeborieOverride(Base):
    """Ручное место жюри в двоеборье категории.

    Ставится в десктопе в окне «Итоги двоеборья», когда у спортсменов
    равные очки И равный вес, и нужно вручную выбрать победителя «спорной»
    группы. Синхронизируется на сайт и применяется в _category_standings:
    участник с manual_rank внутри группы получает отдельное (более высокое)
    место, остальные в группе делят следующее.
    """

    __tablename__ = "dvoeborie_overrides"

    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("competition_participants.id", ondelete="CASCADE"), primary_key=True
    )
    manual_rank: Mapped[int] = mapped_column(Integer, nullable=False)
