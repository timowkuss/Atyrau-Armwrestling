from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Coach(Base):
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # ─── Карточка тренера в админке: Имя/Фамилия/возраст/ИИН/звание/город.
    # first_name/last_name хранятся отдельно (как у Athlete в десктопе),
    # full_name пересчитывается сервером при сохранении и остаётся
    # единственным полем для отображения/поиска — чтобы не трогать уже
    # существующие места, где используется coach.full_name.
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    birth_date: Mapped[date | None] = mapped_column(Date)
    # ИИН — 12 цифр. У старых записей может отсутствовать, поэтому nullable
    # на уровне БД, но обязателен в CoachCreate для новых тренеров.
    iin: Mapped[str | None] = mapped_column(String(12), unique=True)
    # Телефон — виден только админу и десктопу (в публичных ответах не
    # отдаётся). Нормализуется к виду 8(702)313-53-83.
    phone: Mapped[str | None] = mapped_column(String(30))
    # Тренерское звание (не путать с Athlete.rank — спортивный разряд).
    qualification: Mapped[str | None] = mapped_column(String(100))
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL")
    )

    photo_path: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(Text)

    # Скрытые тренеры (см. is_hidden у Athlete): админка «удаляет» тренера,
    # но полностью стереть его нельзя — карточку прячем, оставаясь
    # доступной в секции «Скрытые». Скрытые тренеры не показываются на
    # публичном сайте, в админке/десктопе — только в отдельной секции.
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    club: Mapped["Club"] = relationship(back_populates="coaches")
    city: Mapped["City"] = relationship()
    athletes: Mapped[list["Athlete"]] = relationship(back_populates="coach")
