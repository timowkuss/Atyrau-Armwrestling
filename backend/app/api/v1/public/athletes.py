from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, extract, func, or_
from sqlalchemy.orm import Session, joinedload

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
    AthleteBirthdayOut,
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
            func.coalesce(
                (AthleteStatistic.elo_left + AthleteStatistic.elo_right) / 2,
                0
            ).label("elo_combined"),
        )
        .outerjoin(Club, Athlete.club_id == Club.id)
        .outerjoin(Coach, Athlete.coach_id == Coach.id)
        .outerjoin(City, Athlete.city_id == City.id)
        .outerjoin(AthleteStatistic, Athlete.id == AthleteStatistic.athlete_id)
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
        query = query.filter(Athlete.rank.ilike(f"%{rank}%"))
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
            club_id=athlete.club_id,
            coach_name=coach_name,
            city_name=city_name,
            rank=athlete.rank,
            photo_path=athlete.photo_path,
            elo_combined=round(elo_combined or 0),
        )
        for athlete, club_name, coach_name, city_name, elo_combined in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/birthdays", response_model=list[AthleteBirthdayOut])
def upcoming_birthdays(db: Session = Depends(get_db)):
    """Именинники на сегодня и завтра для блока на главной странице.

    day_offset: 0 — день рождения сегодня, 1 — завтра. Выборка идёт по
    месяцу и дню рождения (год не важен), поэтому 29 февраля в невисокосный
    год не находится ни одним из смещений (в такой день праздника нет).
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)

    conditions = []
    for target, offset in ((today, 0), (tomorrow, 1)):
        conditions.append(
            and_(
                extract("month", Athlete.birth_date) == target.month,
                extract("day", Athlete.birth_date) == target.day,
            )
        )

    rows = (
        db.query(Athlete)
        .filter(
            Athlete.is_hidden.is_(False),
            Athlete.birth_date.isnot(None),
            or_(*conditions),
        )
        .order_by(Athlete.full_name)
        .all()
    )

    offset_by_key = {
        (target.month, target.day): offset for target, offset in ((today, 0), (tomorrow, 1))
    }

    items = []
    for athlete in rows:
        b = athlete.birth_date
        offset = offset_by_key[(b.month, b.day)]
        target_year = today.year if offset == 0 else tomorrow.year
        items.append(
            AthleteBirthdayOut(
                id=athlete.id,
                full_name=athlete.full_name,
                photo_path=athlete.photo_path,
                gender=athlete.gender,
                birth_date=b,
                day_offset=offset,
                turns_age=max(0, target_year - b.year),
            )
        )
    return items


@router.get("/{athlete_id}", response_model=AthleteDetailOut)
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    athlete = (
        db.query(Athlete)
        .options(
            joinedload(Athlete.club),
            joinedload(Athlete.coach),
            joinedload(Athlete.city),
            joinedload(Athlete.statistics),
        )
        .filter(Athlete.id == athlete_id, Athlete.is_hidden.is_(False))
        .first()
    )
    if athlete is None:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    stats = None
    if athlete.statistics:
        s = athlete.statistics
        stats = AthleteStatisticsOut(
            total_competitions=s.total_competitions,
            total_wins=s.total_wins,
            total_losses=s.total_losses,
            win_rate=s.win_rate,
            left_hand_wins=s.left_hand_wins,
            left_hand_losses=s.left_hand_losses,
            right_hand_wins=s.right_hand_wins,
            right_hand_losses=s.right_hand_losses,
            gold_count=s.gold_count,
            silver_count=s.silver_count,
            bronze_count=s.bronze_count,
            elo_left=s.elo_left,
            elo_right=s.elo_right,
            elo_combined=elo_combined(s.elo_left, s.elo_right),
        )

    city_name = athlete.city.name if athlete.city else None
    region_name = None
    country_name = None
    if athlete.region_id:
        region = db.get(Region, athlete.region_id)
        region_name = region.name if region else None
    if athlete.country_id:
        country = db.get(Country, athlete.country_id)
        country_name = country.name if country else None

    return AthleteDetailOut(
        id=athlete.id,
        full_name=athlete.full_name,
        birth_date=athlete.birth_date,
        gender=athlete.gender,
        club_name=athlete.club.name if athlete.club else None,
        club_id=athlete.club_id,
        coach_name=athlete.coach.full_name if athlete.coach else None,
        coach_id=athlete.coach_id,
        city_name=city_name,
        region_name=region_name,
        country_name=country_name,
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

    # Собираем все CompetitionParticipant id и загружаем одним запросом
    pids = set()
    for match, _, _ in matches:
        if match.p1_id:
            pids.add(match.p1_id)
        if match.p2_id:
            pids.add(match.p2_id)
        if match.winner_id:
            pids.add(match.winner_id)
    participants = {
        cp.id: cp
        for cp in (
            db.query(CompetitionParticipant)
            .options(joinedload(CompetitionParticipant.athlete))
            .filter(CompetitionParticipant.id.in_(pids))
            .all()
        )
    } if pids else {}

    items = []
    for match, competition, category in matches:
        p1 = participants.get(match.p1_id) if match.p1_id else None
        p2 = participants.get(match.p2_id) if match.p2_id else None
        opponent = None
        if p1 and p1.athlete_id == athlete_id and p2:
            opponent = p2.athlete.full_name
        elif p2 and p2.athlete_id == athlete_id and p1:
            opponent = p1.athlete.full_name

        is_winner = None
        if match.winner_id is not None:
            winner = participants.get(match.winner_id)
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
