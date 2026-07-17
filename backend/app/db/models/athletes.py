from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Athlete(Base):
    """Спортсмен создаётся один раз и хранится в единой центральной базе.
    Десктоп-приложение и сайт работают с одной и той же записью (см.
    ARCHITECTURE.md, §0 и §5 — модель реального времени).

    ПРИМЕЧАНИЕ (обнаружено на Этапе 6): существующее десктоп-приложение не
    собирает пол участника (только вес/категорию/руку), поэтому gender
    здесь nullable — заполняется при синхронизации, если известен, иначе
    донабирается позже вручную через сайт. Рекомендация на будущее:
    добавить необязательное поле "пол" в форму участника в десктопе."""

    __tablename__ = "athletes"
    __table_args__ = (
        CheckConstraint(
            "gender is null or gender in ('male','female')", name="ck_athletes_gender"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(10))

    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL")
    )
    coach_id: Mapped[int | None] = mapped_column(
        ForeignKey("coaches.id", ondelete="SET NULL")
    )
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL")
    )
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id", ondelete="SET NULL")
    )
    country_id: Mapped[int | None] = mapped_column(
        ForeignKey("countries.id", ondelete="SET NULL")
    )

    rank: Mapped[str | None] = mapped_column(String(50))  # разряд
    photo_path: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(Text)

    # тот же формат ARM###### что использует BadgeGenerator в десктопе
    external_barcode_id: Mapped[str | None] = mapped_column(String(30), unique=True)

    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    club: Mapped["Club"] = relationship(back_populates="athletes")
    coach: Mapped["Coach"] = relationship(back_populates="athletes")
    statistics: Mapped["AthleteStatistic"] = relationship(
        back_populates="athlete", uselist=False, cascade="all, delete-orphan"
    )
