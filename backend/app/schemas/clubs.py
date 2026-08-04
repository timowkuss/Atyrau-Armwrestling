from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, field_validator


# Телефон приводится к единому виду 8(702)313-53-83. Пробелы/скобки/дефисы/+
# игнорируем; «8…» или «7…» в начале снимаем только когда это код страны
# (всего 11 цифр), а десятизначный номер оставляем как есть.
def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", value.strip())
    if not digits:
        return None
    if len(digits) == 11 and digits[0] in "87":
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Телефон должен быть в формате 8(XXX)XXX-XX-XX")
    return f"8({digits[0:3]}){digits[3:6]}-{digits[6:8]}-{digits[8:]}"


class ClubListOut(BaseModel):
    id: int
    name: str
    logo_path: str | None
    address: str | None = None
    phone: str | None = None
    city_name: str | None
    rating_points: int
    athletes_count: int
    coaches_count: int = 0


class ClubDetailOut(BaseModel):
    id: int
    name: str
    logo_path: str | None
    description: str | None
    address: str | None = None
    phone: str | None = None
    city_name: str | None
    founded_date: date | None
    rating_points: int
    athletes_count: int
    coaches_count: int
    athletes: list[ClubMemberOut] = []
    coaches: list[ClubMemberOut] = []


class ClubCreate(BaseModel):
    name: str
    logo_path: str | None = None
    description: str | None = None
    address: str | None = None
    phone: str | None = None
    city_id: int | None = None
    founded_date: date | None = None

    _validate_phone_field = field_validator("phone")(_validate_phone)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Поле не может быть пустым")
        return value


class ClubUpdate(BaseModel):
    name: str | None = None
    logo_path: str | None = None
    description: str | None = None
    address: str | None = None
    phone: str | None = None
    city_id: int | None = None
    founded_date: date | None = None
    # rating_points НЕ включён намеренно: это агрегат, который должен
    # считаться от результатов турниров, а не править руками напрямую.

    _validate_phone_field = field_validator("phone")(_validate_phone)


class ClubMemberOut(BaseModel):
    id: int
    full_name: str
    photo_path: str | None = None


class ClubAdminListOut(BaseModel):
    id: int
    name: str
    logo_path: str | None
    description: str | None
    address: str | None = None
    phone: str | None = None
    city_id: int | None
    city_name: str | None
    founded_date: date | None
    rating_points: int
    athletes_count: int
    coaches_count: int


class ClubAdminDetailOut(ClubAdminListOut):
    athletes: list[ClubMemberOut]
    coaches: list[ClubMemberOut]


class ClubMembersAdd(BaseModel):
    athlete_ids: list[int] = []
    coach_ids: list[int] = []


class ClubRatingHistoryItemOut(BaseModel):
    """Одна запись истории изменения рейтинга клуба."""

    id: int
    created_at: datetime
    points: int
    reason: str
    description: str
    athlete_name: str | None = None
    tournament_name: str | None = None


class ClubRatingOut(BaseModel):
    """Текущий рейтинг клуба + журнал изменений."""

    rating: int
    history: list[ClubRatingHistoryItemOut] = []
