from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ClubListOut(BaseModel):
    id: int
    name: str
    logo_path: str | None
    address: str | None = None
    city_name: str | None
    rating_points: int
    athletes_count: int


class ClubDetailOut(BaseModel):
    id: int
    name: str
    logo_path: str | None
    description: str | None
    address: str | None = None
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
    city_id: int | None = None
    founded_date: date | None = None


class ClubUpdate(BaseModel):
    name: str | None = None
    logo_path: str | None = None
    description: str | None = None
    address: str | None = None
    city_id: int | None = None
    founded_date: date | None = None
    # rating_points НЕ включён намеренно: это агрегат, который должен
    # считаться от результатов турниров, а не править руками напрямую.


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
