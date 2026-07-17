from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.rankings import AthleteRanking, ClubRanking
from app.db.session import get_db
from app.schemas.common import AthleteRankingOut, ClubRankingOut

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
