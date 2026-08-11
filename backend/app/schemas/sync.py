from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    """Все sync-схемы, принимающие данные от десктопа, используют
    extra='forbid'. Если десктоп пошлёт поле, которого нет в схеме,
    Pydantic вернёт 422 ValidationError — ошибка сразу видна в логах,
    а не замалчивается (как было с coach_name в AthleteSyncUpdate)."""

    model_config = ConfigDict(extra="forbid")


class AthleteSearchResultItem(BaseModel):
    id: int
    full_name: str
    club_name: str | None
    birth_date: str | None
    gender: str | None


class AthleteSyncCreate(_StrictModel):
    """Создание спортсмена из десктопа. gender/birth_date опциональны —
    десктоп-приложение сегодня их не собирает (см. примечание в
    app/db/models/athletes.py и ARCHITECTURE.md §0, находка Этапа 6)."""

    full_name: str
    club_name: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    rank: str | None = None
    photo_path: str | None = None
    coach_name: str | None = None
    iin: str | None = None
    phone: str | None = None


class AthleteSyncUpdate(_StrictModel):
    """PATCH из десктопа: приходят только изменённые поля."""

    full_name: str | None = None
    club_name: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    rank: str | None = None
    photo_path: str | None = None
    coach_name: str | None = None
    iin: str | None = None
    phone: str | None = None
    is_hidden: bool | None = None


class CoachSyncCreate(_StrictModel):
    """Создание тренера из десктопа."""

    full_name: str
    club_name: str | None = None
    photo_path: str | None = None
    bio: str | None = None
    # Добавлено вместе с карточкой тренера в админке (Имя/Фамилия/возраст/
    # ИИН/звание/город) — те же поля десктоп теперь тоже собирает и шлёт.
    first_name: str | None = None
    last_name: str | None = None
    birth_date: str | None = None  # 'YYYY-MM-DD'
    iin: str | None = None
    qualification: str | None = None
    city_name: str | None = None  # best-effort сопоставление с cities.name
    phone: str | None = None


class CoachSyncUpdate(_StrictModel):
    """PATCH из десктопа: приходят только изменённые поля."""

    full_name: str | None = None
    club_name: str | None = None
    photo_path: str | None = None
    bio: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    birth_date: str | None = None
    iin: str | None = None
    qualification: str | None = None
    city_name: str | None = None
    phone: str | None = None
    is_hidden: bool | None = None


class CompetitionSyncCreate(_StrictModel):
    name: str
    date: str
    location_name: str | None = None  # текстом из десктопа; сервер best-effort
    # сопоставляет с cities.name, иначе оставляет location_city_id пустым.
    weight_tolerance: float | None = None
    bracket_system: str | None = None  # 'double' | 'single'
    format_type: str | None = None  # 'combined' (двоеборье) | 'separate'


class CategorySyncCreate(_StrictModel):
    name: str
    max_weight: float | None = None
    hand: str = "Обе"


class CompetitionParticipantSyncCreate(_StrictModel):
    local_participant_id: int  # для диагностики/логов, не хранится
    athlete_id: int
    category_id: int  # ЦЕНТРАЛЬНЫЙ id категории (из ответа CategorySyncCreate)
    weight_at_event: float | None = None
    club_at_event: str | None = None


class MatchSyncCreate(_StrictModel):
    # Локальный id матча из десктопа (таблица matches в armwrestling.db).
    # Используется сервером как идемпотентный ключ: повторный POST с тем же
    # (category_id, mid) — это ретрай после потерянного ответа, а не новый
    # матч, сервер вернёт существующий id вместо создания дубля.
    mid: int | None = Field(default=None, ge=0)
    category_id: int  # центральный id
    hand: Literal["Правая", "Левая", "Обе"] = "Правая"
    round_name: str | None = None
    bracket: Literal["winners", "losers", "final"] = "winners"
    match_order: int = Field(default=0, ge=0)
    stage: int = Field(default=0, ge=0)
    p1_id: int | None = None  # центральный id competition_participants
    p2_id: int | None = None
    winner_id: int | None = None
    p1_losses: int = Field(default=0, ge=0, le=2)
    p2_losses: int = Field(default=0, ge=0, le=2)
    is_bye: bool = False
    status: Literal["pending", "waiting", "done", "bye"] = "pending"
    table_number: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _winner_is_participant(self):
        # Победитель обязан быть одним из участников матча: клиент не может
        # «назначить» победителем произвольного участника чужой категории.
        if self.winner_id is not None and self.winner_id not in (
            self.p1_id,
            self.p2_id,
        ):
            raise ValueError(
                "winner_id должен совпадать с p1_id или p2_id"
            )
        return self


class MatchSyncBatchCreate(_StrictModel):
    """Пакетное создание матчей (см. POST /sync/matches/batch).

    Один HTTP-запрос вместо тысячи: при синхронизации сетки турнира из
    десктопа каждый матч раньше уходил отдельным POST (4000-6000 запросов
    на турнир), что давило и сеть, и пул соединений, и очередь БД.
    Лимит размера пакета защищает от DoS гигантским телом запроса."""

    matches: list[MatchSyncCreate] = Field(default_factory=list, max_length=10000)


class MatchSyncUpdate(_StrictModel):
    p1_id: int | None = None
    p2_id: int | None = None
    winner_id: int | None = None
    p1_losses: int | None = Field(default=None, ge=0, le=2)
    p2_losses: int | None = Field(default=None, ge=0, le=2)
    status: Literal["pending", "waiting", "done", "bye"] | None = None
    table_number: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _winner_is_participant(self):
        # winner_id из update обязан быть p1_id или p2_id (на момент
        # обновления), если оба известны; если один из участников ещё
        # не определён — победа невозможна, winner_id должен быть None.
        if self.winner_id is not None:
            if self.p1_id is None and self.p2_id is None:
                raise ValueError(
                    "winner_id нельзя задать без участников матча"
                )
            if self.p1_id is not None and self.p2_id is not None:
                if self.winner_id not in (self.p1_id, self.p2_id):
                    raise ValueError(
                        "winner_id должен совпадать с p1_id или p2_id"
                    )
        return self


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
    coach_name: str | None
    iin: str | None = None
    phone: str | None = None
    is_hidden: bool
    updated_at: str


class AthleteChangesOut(BaseModel):
    server_time: str  # десктоп сохраняет как курсор для следующего запроса
    updated: list[AthleteChangeItem]
    deleted: list[int]  # центральные id жёстко удалённых спортсменов


class CoachChangeItem(BaseModel):
    """Одна карточка тренера, изменённая через админку сайта, для
    подтягивания в десктоп (см. GET /sync/coaches/changes)."""

    id: int
    full_name: str
    club_name: str | None
    photo_path: str | None
    bio: str | None
    first_name: str | None = None
    last_name: str | None = None
    birth_date: str | None = None
    iin: str | None = None
    qualification: str | None = None
    city_name: str | None = None
    phone: str | None = None
    is_hidden: bool
    updated_at: str


class CoachChangesOut(BaseModel):
    server_time: str
    updated: list[CoachChangeItem]
    deleted: list[int]  # центральные id жёстко удалённых тренеров


class ClubSyncItem(BaseModel):
    """Клуб из центральной базы для десктопа (GET /sync/clubs)."""

    id: int
    name: str
    address: str | None = None
    city_name: str | None = None
    founded_date: str | None = None
    logo_path: str | None = None
    phone: str | None = None


class ClubSyncCreate(_StrictModel):
    """Создание клуба из десктопа."""

    name: str
    address: str | None = None
    city_name: str | None = None
    founded_date: str | None = None
    logo_path: str | None = None
    phone: str | None = None


class ClubSyncUpdate(_StrictModel):
    """PATCH из десктопа: приходят только изменённые поля."""

    name: str | None = None
    address: str | None = None
    city_name: str | None = None
    founded_date: str | None = None
    logo_path: str | None = None
    phone: str | None = None
