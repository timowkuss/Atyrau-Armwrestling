from datetime import date

from pydantic import BaseModel


class AthleteListOut(BaseModel):
    id: int
    full_name: str
    birth_date: date | None
    gender: str | None
    club_name: str | None
    coach_name: str | None
    city_name: str | None
    rank: str | None
    photo_path: str | None


class AthleteAdminListOut(AthleteListOut):
    is_hidden: bool


class AthleteStatisticsOut(BaseModel):
    total_competitions: int
    total_wins: int
    total_losses: int
    win_rate: float
    left_hand_wins: int
    left_hand_losses: int
    right_hand_wins: int
    right_hand_losses: int
    gold_count: int
    silver_count: int
    bronze_count: int
    # elo_left/elo_right — независимые рейтинги по руке (см.
    # app/services/elo_engine.py). elo_combined нигде не хранится, это
    # (elo_left + elo_right) / 2, посчитанное на момент ответа — тот самый
    # "общий Эло", который на сайте показывается крупно, а лев/прав
    # раскрываются по клику.
    elo_left: int
    elo_right: int
    elo_combined: int


class AthleteDetailOut(BaseModel):
    id: int
    full_name: str
    birth_date: date | None
    gender: str | None
    club_name: str | None
    coach_name: str | None
    city_name: str | None
    region_name: str | None
    country_name: str | None
    rank: str | None
    photo_path: str | None
    bio: str | None
    statistics: AthleteStatisticsOut | None


class AthleteCompetitionHistoryItem(BaseModel):
    competition_id: int
    competition_name: str
    date: date
    category_name: str
    place: int | None
    medal: str


class AthleteMatchHistoryItem(BaseModel):
    match_id: int
    competition_id: int
    competition_name: str
    category_name: str
    round_name: str | None
    opponent_name: str | None
    is_winner: bool | None


class AthleteCreate(BaseModel):
    full_name: str
    birth_date: date | None = None
    gender: str | None = None
    club_id: int | None = None
    coach_id: int | None = None
    city_id: int | None = None
    region_id: int | None = None
    country_id: int | None = None
    rank: str | None = None
    photo_path: str | None = None
    bio: str | None = None


class AthleteUpdate(BaseModel):
    full_name: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    club_id: int | None = None
    coach_id: int | None = None
    city_id: int | None = None
    region_id: int | None = None
    country_id: int | None = None
    rank: str | None = None
    photo_path: str | None = None
    bio: str | None = None
    is_hidden: bool | None = None
    # external_barcode_id НЕ включён — это идентификатор из десктопа
    # (BadgeGenerator), сайт его не назначает и не меняет.


class AthleteStatisticsUpdate(BaseModel):
    """Любое подмножество полей athlete_statistics. Сохранение через
    PATCH /admin/athletes/{id}/statistics автоматически ставит
    is_manual_override=true (см. ARCHITECTURE.md §3.4, §4.2, §6)."""

    total_competitions: int | None = None
    total_wins: int | None = None
    total_losses: int | None = None
    win_rate: float | None = None
    left_hand_wins: int | None = None
    left_hand_losses: int | None = None
    right_hand_wins: int | None = None
    right_hand_losses: int | None = None
    gold_count: int | None = None
    silver_count: int | None = None
    bronze_count: int | None = None
    elo_left: int | None = None
    elo_right: int | None = None


class AthleteStatisticsAdminOut(AthleteStatisticsOut):
    is_manual_override: bool
    overridden_by: int | None
    overridden_at: str | None
