from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Result(Base):
    """Итоговое место/медаль спортсмена в категории турнира. Пишется на
    шаге "Опубликовать результаты" (см. publish_pipeline.py, Этап 7)."""

    __tablename__ = "results"
    __table_args__ = (
        CheckConstraint(
            "medal in ('gold','silver','bronze','none')", name="ck_results_medal"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    competition_participant_id: Mapped[int] = mapped_column(
        ForeignKey("competition_participants.id", ondelete="CASCADE"), nullable=False
    )

    place: Mapped[int | None] = mapped_column(Integer)
    medal: Mapped[str] = mapped_column(String(10), default="none", nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
