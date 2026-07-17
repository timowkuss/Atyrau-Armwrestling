from pydantic import BaseModel


class ClubListOut(BaseModel):
    id: int
    name: str
    logo_path: str | None
    city_name: str | None
    rating_points: int
    athletes_count: int


class ClubDetailOut(BaseModel):
    id: int
    name: str
    logo_path: str | None
    description: str | None
    city_name: str | None
    founded_year: int | None
    rating_points: int
    athletes_count: int
    coaches_count: int


class ClubCreate(BaseModel):
    name: str
    logo_path: str | None = None
    description: str | None = None
    city_id: int | None = None
    founded_year: int | None = None


class ClubUpdate(BaseModel):
    name: str | None = None
    logo_path: str | None = None
    description: str | None = None
    city_id: int | None = None
    founded_year: int | None = None
    # rating_points НЕ включён намеренно: это агрегат, который должен
    # считаться от результатов турниров, а не править руками напрямую.
