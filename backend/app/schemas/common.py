from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class AthleteRankingOut(BaseModel):
    position: int | None
    athlete_id: int
    athlete_name: str
    club_name: str | None
    points: int
    period: str | None


class ClubRankingOut(BaseModel):
    position: int | None
    club_id: int
    club_name: str
    points: int
    gold_count: int
    silver_count: int
    bronze_count: int
