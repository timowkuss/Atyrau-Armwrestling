from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.rankings import AthleteRanking, ClubRanking
from app.db.session import get_db
from app.schemas.common import AthleteRankingOut, ClubRankingOut, CoachRankingOut

router = APIRouter(prefix="/rankings", tags=["public:rankings"])


@router.get("/athletes", response_model=list[AthleteRankingOut])
def athlete_rankings(
    period: str | None = None,
    gender: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AthleteRanking, Athlete.full_name, Club.name.label("club_name")).join(
        Athlete, AthleteRanking.athlete_id == Athlete.id
    ).outerjoin(Club, Athlete.club_id == Club.id)
    if period:
        query = query.filter(AthleteRanking.period == period)
    if gender:
        query = query.filter(AthleteRanking.scope_gender == gender)
    rows = query.order_by(AthleteRanking.points.desc()).limit(limit).all()
    return [
        AthleteRankingOut(
            position=r.position, athlete_id=r.athlete_id, athlete_name=name,
            club_name=club_name, points=r.points, period=r.period,
        )
        for r, name, club_name in rows
    ]


@router.get("/coaches", response_model=list[CoachRankingOut])
def coach_rankings(
    period: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    # Своей таблицы рейтинга тренеров пока нет — считаем прямо здесь,
    # суммируя очки уже накопленного рейтинга спортсменов по их тренеру
    # (Athlete.coach_id). Тренеры без учеников или без очков в выдачу не
    # попадают — их рейтинг просто пока не из чего считать.
    query = (
        db.query(
            Coach.id,
            Coach.full_name,
            Club.name.label("club_name"),
            func.count(func.distinct(Athlete.id)).label("athletes_count"),
            func.coalesce(func.sum(AthleteRanking.points), 0).label("points"),
        )
        .join(Athlete, Athlete.coach_id == Coach.id)
        .join(AthleteRanking, AthleteRanking.athlete_id == Athlete.id)
        .outerjoin(Club, Coach.club_id == Club.id)
    )
    if period:
        query = query.filter(AthleteRanking.period == period)
    rows = (
        query.group_by(Coach.id, Coach.full_name, Club.name)
        .having(func.coalesce(func.sum(AthleteRanking.points), 0) > 0)
        .order_by(func.sum(AthleteRanking.points).desc())
        .limit(limit)
        .all()
    )
    return [
        CoachRankingOut(
            position=i + 1, coach_id=coach_id, coach_name=full_name,
            club_name=club_name, athletes_count=athletes_count, points=int(points),
        )
        for i, (coach_id, full_name, club_name, athletes_count, points) in enumerate(rows)
    ]


@router.get("/clubs", response_model=list[ClubRankingOut])
def club_rankings(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    rows = (
        db.query(ClubRanking, Club.name)
        .join(Club, ClubRanking.club_id == Club.id)
        .order_by(ClubRanking.points.desc())
        .limit(limit)
        .all()
    )
    return [
        ClubRankingOut(
            position=r.position, club_id=r.club_id, club_name=name, points=r.points,
            gold_count=r.gold_count, silver_count=r.silver_count, bronze_count=r.bronze_count,
        )
        for r, name in rows
    ]
