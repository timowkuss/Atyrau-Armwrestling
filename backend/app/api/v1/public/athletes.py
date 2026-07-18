from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.geo import City, Country, Region
from app.db.models.matches import Match
from app.db.models.results import Result
from app.db.models.statistics import AthleteStatistic
from app.db.session import get_db
from app.schemas.athletes import (
    AthleteCompetitionHistoryItem,
    AthleteDetailOut,
    AthleteListOut,
    AthleteMatchHistoryItem,
    AthleteStatisticsOut,
)
from app.schemas.common import Page
from app.services.elo_engine import elo_combined

router = APIRouter(prefix="/athletes", tags=["public:athletes"])


@router.get("", response_model=Page[AthleteListOut])
def list_athletes(
    name: str | None = None,
    club_id: int | None = None,
    city_id: int | None = None,
    coach_id: int | None = None,
    age: int | None = None,
    weight_category_id: int | None = None,
    rank: str | None = None,
    gender: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            Athlete,
            Club.name.label("club_name"),
            Coach.full_name.label("coach_name"),
            City.name.label("city_name"),
        )
        .outerjoin(Club, Athlete.club_id == Club.id)
        .outerjoin(Coach, Athlete.coach_id == Coach.id)
        .outerjoin(City, Athlete.city_id == City.id)
        .filter(Athlete.is_hidden.is_(False))
    )

    if name:
        query = query.filter(Athlete.full_name.ilike(f"%{name}%"))
    if club_id is not None:
        query = query.filter(Athlete.club_id == club_id)
    if city_id is not None:
        query = query.filter(Athlete.city_id == city_id)
    if coach_id is not None:
        query = query.filter(Athlete.coach_id == coach_id)
    if rank:
        query = query.filter(Athlete.rank == rank)
    if gender:
        query = query.filter(Athlete.gender == gender)
    if age is not None:
        query = query.filter(
            func.date_part("year", func.age(Athlete.birth_date)) == age
        )
    if weight_category_id is not None:
        athlete_ids_in_weight = (
            db.query(CompetitionParticipant.athlete_id)
            .join(Category, CompetitionParticipant.category_id == Category.id)
            .filter(Category.weight_category_id == weight_category_id)
            .distinct()
        )
        query = query.filter(Athlete.id.in_(athlete_ids_in_weight))

    total = query.count()
    rows = (
        query.order_by(Athlete.full_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        AthleteListOut(
            id=athlete.id,
            full_name=athlete.full_name,
            birth_date=athlete.birth_date,
            gender=athlete.gender,
            club_name=club_name,
            coach_name=coach_name,
            city_name=city_name,
            rank=athlete.rank,
            photo_path=athlete.photo_path,
        )
        for athlete, club_name, coach_name, city_name in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{athlete_id}", response_model=AthleteDetailOut)
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    athlete = (
        db.query(Athlete)
        .filter(Athlete.id == athlete_id, Athlete.is_hidden.is_(False))
        .first()
    )
    if athlete is None:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    stats_row = (
        db.query(AthleteStatistic).filter(AthleteStatistic.athlete_id == athlete.id).first()
    )
    stats = (
        AthleteStatisticsOut(
            total_competitions=stats_row.total_competitions,
            total_wins=stats_row.total_wins,
            total_losses=stats_row.total_losses,
            win_rate=stats_row.win_rate,
            left_hand_wins=stats_row.left_hand_wins,
            left_hand_losses=stats_row.left_hand_losses,
            right_hand_wins=stats_row.right_hand_wins,
            right_hand_losses=stats_row.right_hand_losses,
            gold_count=stats_row.gold_count,
            silver_count=stats_row.silver_count,
            bronze_count=stats_row.bronze_count,
            elo_left=stats_row.elo_left,
            elo_right=stats_row.elo_right,
            elo_combined=elo_combined(stats_row.elo_left, stats_row.elo_right),
        )
        if stats_row
        else None
    )

    city_name = (
        db.get(City, athlete.city_id).name if athlete.city_id else None
    )

    return AthleteDetailOut(
        id=athlete.id,
        full_name=athlete.full_name,
        birth_date=athlete.birth_date,
        gender=athlete.gender,
        club_name=athlete.club.name if athlete.club else None,
        coach_name=athlete.coach.full_name if athlete.coach else None,
        city_name=city_name,
        region_name=(
            db.get(Region, athlete.region_id).name if athlete.region_id else None
        ),
        country_name=(
            db.get(Country, athlete.country_id).name if athlete.country_id else None
        ),
        rank=athlete.rank,
        photo_path=athlete.photo_path,
        bio=athlete.bio,
        statistics=stats,
    )


@router.get("/{athlete_id}/history", response_model=list[AthleteCompetitionHistoryItem])
def get_athlete_history(athlete_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(
            Competition.id.label("competition_id"),
            Competition.name.label("competition_name"),
            Competition.date,
            Category.name.label("category_name"),
            Result.place,
            Result.medal,
        )
        .join(CompetitionParticipant, CompetitionParticipant.competition_id == Competition.id)
        .join(Category, CompetitionParticipant.category_id == Category.id)
        .outerjoin(
            Result, Result.competition_participant_id == CompetitionParticipant.id
        )
        .filter(
            CompetitionParticipant.athlete_id == athlete_id,
            Competition.status == "published",
        )
        .order_by(Competition.date.desc())
        .all()
    )
    return [
        AthleteCompetitionHistoryItem(
            competition_id=r.competition_id,
            competition_name=r.competition_name,
            date=r.date,
            category_name=r.category_name,
            place=r.place,
            medal=r.medal or "none",
        )
        for r in rows
    ]


@router.get("/{athlete_id}/matches", response_model=list[AthleteMatchHistoryItem])
def get_athlete_matches(athlete_id: int, db: Session = Depends(get_db)):
    P1 = CompetitionParticipant
    matches = (
        db.query(Match, Competition, Category)
        .join(Competition, Match.competition_id == Competition.id)
        .join(Category, Match.category_id == Category.id)
        .join(
            P1,
            or_(Match.p1_id == P1.id, Match.p2_id == P1.id),
        )
        .filter(P1.athlete_id == athlete_id, Competition.status == "published")
        .order_by(Competition.date.desc())
        .all()
    )

    items = []
    for match, competition, category in matches:
        p1 = db.get(CompetitionParticipant, match.p1_id) if match.p1_id else None
        p2 = db.get(CompetitionParticipant, match.p2_id) if match.p2_id else None
        opponent = None
        if p1 and p1.athlete_id == athlete_id and p2:
            opponent = p2.athlete.full_name
        elif p2 and p2.athlete_id == athlete_id and p1:
            opponent = p1.athlete.full_name

        is_winner = None
        if match.winner_id is not None:
            winner = db.get(CompetitionParticipant, match.winner_id)
            if winner is not None:
                is_winner = winner.athlete_id == athlete_id

        items.append(
            AthleteMatchHistoryItem(
                match_id=match.id,
                competition_id=competition.id,
                competition_name=competition.name,
                category_name=category.name,
                round_name=match.round_name,
                opponent_name=opponent,
                is_winner=is_winner,
            )
        )
    return items
