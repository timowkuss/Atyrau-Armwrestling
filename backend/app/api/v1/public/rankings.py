from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.rankings import AthleteRanking, ClubRanking
from app.db.models.statistics import AthleteStatistic
from app.db.session import get_db
from app.schemas.common import AthleteRankingOut, ClubRankingOut, CoachRankingOut, EloRankingOut
from app.services.coach_rating import calculate_coach_rating

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
    ).join(AthleteStatistic, Athlete.id == AthleteStatistic.athlete_id
    ).outerjoin(Club, Athlete.club_id == Club.id)
    if period:
        query = query.filter(AthleteRanking.period == period)
    if gender:
        query = query.filter(AthleteRanking.scope_gender == gender)
    rows = query.order_by(
        AthleteRanking.points.desc(),
        AthleteStatistic.win_rate.desc(),
        AthleteStatistic.gold_count.desc(),
        AthleteStatistic.silver_count.desc(),
        AthleteStatistic.bronze_count.desc(),
        Athlete.id.asc(),
    ).limit(limit).all()
    return [
        AthleteRankingOut(
            position=i + 1, athlete_id=r.athlete_id, athlete_name=name,
            club_name=club_name, points=r.points, period=r.period,
        )
        for i, (r, name, club_name) in enumerate(rows)
    ]


@router.get("/coaches", response_model=list[CoachRankingOut])
def coach_rankings(
    name: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    coaches = db.query(Coach).outerjoin(Club, Coach.club_id == Club.id).add_columns(
        Club.name.label("club_name"),
    )
    coaches = coaches.filter(Coach.is_hidden.is_(False))
    if name:
        coaches = coaches.filter(Coach.full_name.ilike(f"%{name}%"))
    rows = coaches.all()
    rankings = []
    for c, club_name in rows:
        r = calculate_coach_rating(db, c.id)
        rankings.append({
            "coach_id": c.id,
            "coach_name": c.full_name,
            "club_name": club_name,
            "photo_path": c.photo_path,
            "athletes_count": r["student_count"],
            "points": r["rating"],
        })
    rankings.sort(key=lambda x: (x["points"], x["athletes_count"], -x["coach_id"]), reverse=True)
    return [
        CoachRankingOut(position=i + 1, **r)
        for i, r in enumerate(rankings[:limit])
    ]


@router.get("/clubs", response_model=list[ClubRankingOut])
def club_rankings(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    rows = (
        db.query(ClubRanking, Club.name)
        .join(Club, ClubRanking.club_id == Club.id)
        .order_by(
            ClubRanking.points.desc(),
            ClubRanking.gold_count.desc(),
            ClubRanking.silver_count.desc(),
            ClubRanking.bronze_count.desc(),
            Club.id.asc(),
        )
        .limit(limit)
        .all()
    )
    return [
        ClubRankingOut(
            position=i + 1, club_id=r.club_id, club_name=name, points=r.points,
            gold_count=r.gold_count, silver_count=r.silver_count, bronze_count=r.bronze_count,
        )
        for i, (r, name) in enumerate(rows)
    ]


@router.get("/elo", response_model=list[EloRankingOut])
def elo_rankings(
    gender: str | None = None,
    hand: str | None = None,
    name: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            Athlete.id,
            Athlete.full_name,
            Club.name.label("club_name"),
            Athlete.photo_path,
            AthleteStatistic.elo_left,
            AthleteStatistic.elo_right,
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
    rows = query.all()
    if hand == "left":
        key_fn = lambda r: (r.elo_left or 0, r.elo_right or 0, r.win_rate or 0.0, -r.id)
    elif hand == "right":
        key_fn = lambda r: (r.elo_right or 0, r.elo_left or 0, r.win_rate or 0.0, -r.id)
    else:
        key_fn = lambda r: (
            (r.elo_left + r.elo_right) / 2 if r.elo_left is not None and r.elo_right is not None else 0,
            r.win_rate or 0.0,
            -r.id,
        )
    ranked = sorted(rows, key=key_fn, reverse=True)[:limit]
    return [
        EloRankingOut(
            position=i + 1,
            athlete_id=r.id,
            athlete_name=r.full_name,
            club_name=r.club_name,
            photo_path=r.photo_path,
            elo_combined=round((r.elo_left + r.elo_right) / 2) if r.elo_left is not None and r.elo_right is not None else 0,
            elo_left=r.elo_left or 0,
            elo_right=r.elo_right or 0,
        )
        for i, r in enumerate(ranked)
    ]



