from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.rankings import AthleteRanking, ClubRanking
from app.db.models.statistics import AthleteStatistic
from app.db.session import get_db
from app.schemas.common import AthleteRankingOut, ClubRankingOut, CoachRankingOut, EloRankingOut
from app.services.coach_rating import calculate_coach_rating
from app.services.ranking_compare import compute_rankings, medal_points

router = APIRouter(prefix="/rankings", tags=["public:rankings"])


@router.get("/athletes", response_model=list[AthleteRankingOut])
def athlete_rankings(
    period: str | None = None,
    gender: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """Рейтинг спортсменов из снапшот-таблицы AthleteRanking.

    Сортировка: очки → медальные очки → винрейт; при полном совпадении —
    одинаковое место (см. ranking_compare.py).
    """
    query = db.query(
        AthleteRanking,
        Athlete.full_name,
        Club.name.label("club_name"),
        AthleteStatistic.gold_count,
        AthleteStatistic.silver_count,
        AthleteStatistic.bronze_count,
        AthleteStatistic.win_rate,
    ).join(
        Athlete, AthleteRanking.athlete_id == Athlete.id
    ).join(
        AthleteStatistic, Athlete.id == AthleteStatistic.athlete_id
    ).outerjoin(Club, Athlete.club_id == Club.id)
    if period:
        query = query.filter(AthleteRanking.period == period)
    if gender:
        query = query.filter(AthleteRanking.scope_gender == gender)

    entries = []
    for r, name, club_name, gold, silver, bronze, wr in query.all():
        entries.append({
            "athlete_id": r.athlete_id,
            "athlete_name": name,
            "club_name": club_name,
            "points": r.points,
            "period": r.period,
            # Внутренние ключи сортировки (не попадают в ответ).
            "_rating": r.points,
            "_medal_points": medal_points(gold, silver, bronze),
            "_winrate": wr or 0.0,
        })

    ranked = compute_rankings(
        entries,
        sort_key=lambda e: (e["_rating"], e["_medal_points"], e["_winrate"]),
        limit=limit,
    )
    return [
        AthleteRankingOut(
            position=e["position"], athlete_id=e["athlete_id"], athlete_name=e["athlete_name"],
            club_name=e["club_name"], points=e["points"], period=e["period"],
        )
        for e in ranked
    ]


@router.get("/coaches", response_model=list[CoachRankingOut])
def coach_rankings(
    name: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """Рейтинг тренеров.

    Основной критерий — рейтинг тренера (calculate_coach_rating). При равенстве
    сравниваются суммарные медальные очки всех учеников, затем количество
    активных учеников; при полном совпадении — одинаковое место.
    """
    coaches = db.query(Coach).outerjoin(Club, Coach.club_id == Club.id).add_columns(
        Club.name.label("club_name"),
    )
    coaches = coaches.filter(Coach.is_hidden.is_(False))
    if name:
        coaches = coaches.filter(Coach.full_name.ilike(f"%{name}%"))
    coach_rows = coaches.all()

    # Суммарные медальные очки учеников по каждому тренеру.
    medal_rows = (
        db.query(
            Athlete.coach_id,
            func.coalesce(func.sum(AthleteStatistic.gold_count), 0),
            func.coalesce(func.sum(AthleteStatistic.silver_count), 0),
            func.coalesce(func.sum(AthleteStatistic.bronze_count), 0),
        )
        .join(AthleteStatistic, Athlete.id == AthleteStatistic.athlete_id)
        .filter(Athlete.coach_id.isnot(None), Athlete.is_hidden.is_(False))
        .group_by(Athlete.coach_id)
        .all()
    )
    student_medal_points = {
        coach_id: medal_points(gold, silver, bronze)
        for coach_id, gold, silver, bronze in medal_rows
    }

    # Количество активных (не скрытых) учеников по каждому тренеру.
    active_rows = (
        db.query(Athlete.coach_id, func.count(Athlete.id))
        .filter(Athlete.coach_id.isnot(None), Athlete.is_hidden.is_(False))
        .group_by(Athlete.coach_id)
        .all()
    )
    active_students = dict(active_rows)

    entries = []
    for c, club_name in coach_rows:
        r = calculate_coach_rating(db, c.id)
        entries.append({
            "coach_id": c.id,
            "coach_name": c.full_name,
            "club_name": club_name,
            "photo_path": c.photo_path,
            "athletes_count": r["student_count"],
            "points": r["rating"],
            "_rating": r["rating"],
            "_medal_points": student_medal_points.get(c.id, 0),
            "_active_students": active_students.get(c.id, 0),
        })

    ranked = compute_rankings(
        entries,
        sort_key=lambda e: (e["_rating"], e["_medal_points"], e["_active_students"]),
        limit=limit,
    )
    return [
        CoachRankingOut(
            position=e["position"], coach_id=e["coach_id"], coach_name=e["coach_name"],
            club_name=e["club_name"], photo_path=e["photo_path"],
            athletes_count=e["athletes_count"], points=e["points"],
        )
        for e in ranked
    ]


@router.get("/clubs", response_model=list[ClubRankingOut])
def club_rankings(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    """Рейтинг клубов.

    Основной критерий — рейтинг клуба (clubs.rating_points, живая
    денормализованная колонка). При равенстве — суммарные медальные очки всех
    спортсменов клуба, затем количество активных спортсменов; при полном
    совпадении — одинаковое место.

    Медальные очки и число активных спортсменов считаются по спортсменам
    клуба на лету (нескрытые карточки), таблица-снапшот ClubRanking
    не используется — она не заполняется приложением.
    """
    clubs = db.query(Club).all()

    # Суммарные медали спортсменов по каждому клубу.
    medal_rows = (
        db.query(
            Athlete.club_id,
            func.coalesce(func.sum(AthleteStatistic.gold_count), 0),
            func.coalesce(func.sum(AthleteStatistic.silver_count), 0),
            func.coalesce(func.sum(AthleteStatistic.bronze_count), 0),
        )
        .join(AthleteStatistic, Athlete.id == AthleteStatistic.athlete_id)
        .filter(Athlete.club_id.isnot(None), Athlete.is_hidden.is_(False))
        .group_by(Athlete.club_id)
        .all()
    )
    club_medals = {
        club_id: (gold, silver, bronze)
        for club_id, gold, silver, bronze in medal_rows
    }

    # Количество активных спортсменов клуба (выступали за него за последние 6 месяцев).
    active_rows = (
        db.query(Athlete.club_id, func.count(Athlete.id))
        .filter(
            Athlete.club_id.isnot(None),
            Athlete.is_hidden.is_(False),
            Athlete.club_active.is_(True),
        )
        .group_by(Athlete.club_id)
        .all()
    )
    active_athletes = dict(active_rows)

    entries = []
    for club in clubs:
        gold, silver, bronze = club_medals.get(club.id, (0, 0, 0))
        entries.append({
            "club_id": club.id,
            "club_name": club.name,
            "points": club.rating_points,
            "gold_count": gold,
            "silver_count": silver,
            "bronze_count": bronze,
            "_rating": club.rating_points,
            "_medal_points": medal_points(gold, silver, bronze),
            "_active_athletes": active_athletes.get(club.id, 0),
        })

    ranked = compute_rankings(
        entries,
        sort_key=lambda e: (e["_rating"], e["_medal_points"], e["_active_athletes"]),
        limit=limit,
    )
    return [
        ClubRankingOut(
            position=e["position"], club_id=e["club_id"], club_name=e["club_name"],
            points=e["points"], gold_count=e["gold_count"], silver_count=e["silver_count"],
            bronze_count=e["bronze_count"],
        )
        for e in ranked
    ]


@router.get("/elo", response_model=list[EloRankingOut])
def elo_rankings(
    gender: str | None = None,
    hand: str | None = None,
    name: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """Рейтинг спортсменов по Эло (отображается на сайте).

    Сортировка: рейтинг (Эло по выбранной руке / усреднённое) → медальные
    очки → винрейт; при полном совпадении — одинаковое место. Сами значения
    Эло не пересчитываются здесь — только порядок мест.
    """
    query = (
        db.query(
            Athlete.id,
            Athlete.full_name,
            Club.name.label("club_name"),
            Athlete.photo_path,
            AthleteStatistic.elo_left,
            AthleteStatistic.elo_right,
            AthleteStatistic.gold_count,
            AthleteStatistic.silver_count,
            AthleteStatistic.bronze_count,
            AthleteStatistic.win_rate,
        )
        .join(AthleteStatistic, Athlete.id == AthleteStatistic.athlete_id)
        .outerjoin(Club, Athlete.club_id == Club.id)
        .filter(Athlete.is_hidden.is_(False))
    )
    if gender:
        query = query.filter(Athlete.gender == gender)
    if name:
        query = query.filter(Athlete.full_name.ilike(f"%{name}%"))

    entries = []
    for r in query.all():
        if hand == "left":
            rating = r.elo_left or 0
        elif hand == "right":
            rating = r.elo_right or 0
        else:
            rating = (
                (r.elo_left + r.elo_right) / 2
                if r.elo_left is not None and r.elo_right is not None
                else 0
            )
        entries.append({
            "athlete_id": r.id,
            "athlete_name": r.full_name,
            "club_name": r.club_name,
            "photo_path": r.photo_path,
            "elo_combined": (
                round((r.elo_left + r.elo_right) / 2)
                if r.elo_left is not None and r.elo_right is not None
                else 0
            ),
            "elo_left": r.elo_left or 0,
            "elo_right": r.elo_right or 0,
            "_rating": rating,
            "_medal_points": medal_points(r.gold_count, r.silver_count, r.bronze_count),
            "_winrate": r.win_rate or 0.0,
        })

    ranked = compute_rankings(
        entries,
        sort_key=lambda e: (e["_rating"], e["_medal_points"], e["_winrate"]),
        limit=limit,
    )
    return [
        EloRankingOut(
            position=e["position"],
            athlete_id=e["athlete_id"],
            athlete_name=e["athlete_name"],
            club_name=e["club_name"],
            photo_path=e["photo_path"],
            elo_combined=e["elo_combined"],
            elo_left=e["elo_left"],
            elo_right=e["elo_right"],
        )
        for e in ranked
    ]
