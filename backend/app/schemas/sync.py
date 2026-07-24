from pydantic import BaseModel


class AthleteSearchResultItem(BaseModel):
    id: int
    full_name: str
    club_name: str | None
    birth_date: str | None
    gender: str | None


class AthleteSyncCreate(BaseModel):
    """Создание спортсмена из десктопа. gender/birth_date опциональны —
    десктоп-приложение сегодня их не собирает (см. примечание в
    app/db/models/athletes.py и ARCHITECTURE.md §0, находка Этапа 6)."""

    full_name: str
    club_name: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    rank: str | None = None
    photo_path: str | None = None


class AthleteSyncUpdate(BaseModel):
    """PATCH из десктопа: приходят только изменённые поля."""

    full_name: str | None = None
    club_name: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    rank: str | None = None
    photo_path: str | None = None


class CompetitionSyncCreate(BaseModel):
    name: str
    date: str
    location_name: str | None = None  # текстом из десктопа; сервер best-effort
    # сопоставляет с cities.name, иначе оставляет location_city_id пустым.
    weight_tolerance: float | None = None
    bracket_system: str | None = None  # 'double' | 'single'
    format_type: str | None = None  # 'combined' (двоеборье) | 'separate'


class CategorySyncCreate(BaseModel):
    name: str
    max_weight: float | None = None
    hand: str = "Обе"


class CompetitionParticipantSyncCreate(BaseModel):
    local_participant_id: int  # для диагностики/логов, не хранится
    athlete_id: int
    category_id: int  # ЦЕНТРАЛЬНЫЙ id категории (из ответа CategorySyncCreate)
    weight_at_event: float | None = None
    club_at_event: str | None = None


class MatchSyncCreate(BaseModel):
    category_id: int  # центральный id
    hand: str = "Правая"
    round_name: str | None = None
    bracket: str = "winners"
    match_order: int = 0
    stage: int = 0
    p1_id: int | None = None  # центральный id competition_participants
    p2_id: int | None = None
    winner_id: int | None = None
    p1_losses: int = 0
    p2_losses: int = 0
    is_bye: bool = False
    status: str = "pending"
    table_number: int | None = None


class MatchSyncUpdate(BaseModel):
    p1_id: int | None = None
    p2_id: int | None = None
    winner_id: int | None = None
    p1_losses: int | None = None
    p2_losses: int | None = None
    status: str | None = None
    table_number: int | None = None


class AthleteChangeItem(BaseModel):
    """Одна карточка спортсмена, изменённая через админку сайта, для
    подтягивания в десктоп (см. GET /sync/athletes/changes)."""

    id: int
    full_name: str
    club_name: str | None
    gender: str | None
    birth_date: str | None
    rank: str | None
    photo_path: str | None
    is_hidden: bool
    updated_at: str


class AthleteChangesOut(BaseModel):
    server_time: str  # десктоп сохраняет как курсор для следующего запроса
    updated: list[AthleteChangeItem]
    deleted: list[int]  # центральные id жёстко удалённых спортсменов
