import re
from datetime import date

from pydantic import BaseModel, field_validator

# Тренерское звание — фиксированный список, синхронизирован со списком
# COACH_QUALIFICATIONS в desktop-app/armwrestling_tournament.py и в
# frontend/src/pages/admin/Coaches/CoachesAdmin.tsx.
COACH_QUALIFICATIONS = [
    "Без категории",
    "Тренер II категории",
    "Тренер I категории",
    "Тренер высшей категории",
    "Заслуженный тренер РК",
]


def _validate_iin(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    if not value:
        return None
    if len(value) != 12 or not value.isdigit():
        raise ValueError("ИИН должен состоять ровно из 12 цифр")
    return value


def _validate_birth_date(value: date | None) -> date | None:
    if value is None:
        return value
    if value > date.today():
        raise ValueError("Дата рождения не может быть в будущем")
    return value


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


class CoachListOut(BaseModel):
    id: int
    full_name: str
    photo_path: str | None
    club_name: str | None
    city_name: str | None
    qualification: str | None
    birth_date: date | None
    athletes_count: int


class CoachDetailOut(BaseModel):
    id: int
    full_name: str
    photo_path: str | None
    bio: str | None
    club_name: str | None
    city_name: str | None
    qualification: str | None
    birth_date: date | None
    athletes_count: int


class CoachAdminListOut(CoachListOut):
    """То же самое, но с ИИН — только для админки (см. GET /admin/coaches).
    first_name/last_name — отдельно, чтобы форма редактирования могла
    предзаполнить поля без разбора full_name по пробелу."""

    iin: str | None
    first_name: str | None
    last_name: str | None
    phone: str | None = None


class CoachAdminDetailOut(CoachDetailOut):
    iin: str | None
    first_name: str | None
    last_name: str | None
    phone: str | None = None


class CoachCreate(BaseModel):
    first_name: str
    last_name: str
    birth_date: date
    iin: str
    qualification: str | None = None
    club_id: int | None = None
    city_id: int | None = None
    photo_path: str | None = None
    bio: str | None = None
    phone: str | None = None

    _validate_iin_field = field_validator("iin")(_validate_iin)
    _validate_birth_date_field = field_validator("birth_date")(_validate_birth_date)
    _validate_phone_field = field_validator("phone")(_validate_phone)

    @field_validator("first_name", "last_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Поле не может быть пустым")
        return value


class CoachUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    birth_date: date | None = None
    iin: str | None = None
    qualification: str | None = None
    club_id: int | None = None
    city_id: int | None = None
    photo_path: str | None = None
    bio: str | None = None
    phone: str | None = None

    _validate_iin_field = field_validator("iin")(_validate_iin)
    _validate_birth_date_field = field_validator("birth_date")(_validate_birth_date)
    _validate_phone_field = field_validator("phone")(_validate_phone)
