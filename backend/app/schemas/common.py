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


class CoachRankingOut(BaseModel):
    position: int | None
    coach_id: int
    coach_name: str
    club_name: str | None
    athletes_count: int
    points: int


class EloRankingOut(BaseModel):
    position: int
    athlete_id: int
    athlete_name: str
    club_name: str | None
    elo_combined: int
    elo_left: int
    elo_right: int


class CoachRatingOut(BaseModel):
    rating: int
    development_score: int
    result_score: int
    scale_score: int
    student_count: int
