from datetime import date

from pydantic import BaseModel, ConfigDict


class CompetitionListOut(BaseModel):
    id: int
    name: str
    date: date
    location_city_name: str | None
    organizer: str | None
    status: str
    participants_count: int


class CategoryOut(BaseModel):
    id: int
    name: str
    hand: str


class CompetitionDetailOut(BaseModel):
    id: int
    name: str
    date: date
    location_city_name: str | None
    organizer: str | None
    description: str | None
    poster_path: str | None
    regulations_doc_path: str | None
    status: str
    participants_count: int
    weight_tolerance: float | None = None
    bracket_system: str | None = None
    format_type: str | None = None
    categories: list[CategoryOut]


class ResultOut(BaseModel):
    category_name: str
    place: int | None
    medal: str
    athlete_id: int
    athlete_name: str
    club_name: str | None


class BracketMatchOut(BaseModel):
    id: int
    category_name: str
    hand: str
    bracket: str
    round_name: str | None
    match_order: int
    p1_name: str | None
    p2_name: str | None
    winner_name: str | None
    status: str


class QueuePairOut(BaseModel):
    match_id: int
    category_name: str
    hand: str
    round_name: str | None
    p1_name: str
    p2_name: str


class TableQueueOut(BaseModel):
    table_number: int
    current: QueuePairOut | None
    next: list[QueuePairOut]


class CompetitionAdminUpdate(BaseModel):
    """Только информационная часть соревнования — сознательно НЕ содержит
    полей сетки/результатов/участников/очков. Их физически нельзя передать
    через этот эндпоинт (см. ARCHITECTURE.md §4.2, §6).
    extra='forbid' — лишнее поле в теле запроса даёт 422."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    poster_path: str | None = None
    regulations_doc_path: str | None = None
    location_city_id: int | None = None
