from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AgeCategory(Base):
    """Федерационный справочник возрастных категорий, напр. 'Юноши 16-17'."""

    __tablename__ = "age_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    min_age: Mapped[int | None] = mapped_column(Integer)
    max_age: Mapped[int | None] = mapped_column(Integer)


class WeightCategory(Base):
    """Федерационный справочник весовых категорий, напр. 'до 80 кг, муж'.
    Используется как для группировки на конкретных турнирах (через Category),
    так и как область видимости для рейтингов (AthleteRanking)."""

    __tablename__ = "weight_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    max_weight: Mapped[float | None] = mapped_column(Float)
    gender: Mapped[str | None] = mapped_column(String(10))


class Category(Base):
    """Категория конкретного турнира (= бывшая weight_categories из
    десктопа), но с привязкой к справочникам и полем 'рука' на уровне
    самой категории, как и раньше."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    weight_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("weight_categories.id", ondelete="SET NULL")
    )
    age_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("age_categories.id", ondelete="SET NULL")
    )
    hand: Mapped[str] = mapped_column(String(20), default="Обе", nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)

    competition: Mapped["Competition"] = relationship(back_populates="categories")
    weight_category: Mapped["WeightCategory"] = relationship()
    age_category: Mapped["AgeCategory"] = relationship()
