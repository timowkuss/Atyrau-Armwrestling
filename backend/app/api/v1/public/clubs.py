from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.geo import City
from app.db.session import get_db
from app.schemas.clubs import (
    ClubDetailOut,
    ClubListOut,
    ClubMemberOut,
    ClubRatingHistoryItemOut,
    ClubRatingOut,
)
from app.schemas.common import Page
from app.services.club_rating import check_inactive_athletes, get_club_rating, get_club_rating_history

router = APIRouter(prefix="/clubs", tags=["public:clubs"])


@router.get("", response_model=Page[ClubListOut])
def list_clubs(
    name: str | None = None,
    city_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            Club,
            City.name.label("city_name"),
            func.count(Athlete.id).label("athletes_count"),
        )
        .outerjoin(City, Club.city_id == City.id)
        .outerjoin(Athlete, (Athlete.club_id == Club.id) & (Athlete.is_hidden.is_(False)))
        .group_by(Club.id, City.name)
    )
    if city_id is not None:
        query = query.filter(Club.city_id == city_id)
    if name:
        query = query.filter(Club.name.ilike(f"%{name}%"))

    total = query.count()
    rows = (
        query.order_by(Club.rating_points.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        ClubListOut(
            id=club.id,
            name=club.name,
            logo_path=club.logo_path,
            address=club.address,
            city_name=city_name,
            rating_points=club.rating_points,
            athletes_count=athletes_count,
        )
        for club, city_name, athletes_count in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{club_id}", response_model=ClubDetailOut)
def get_club(club_id: int, db: Session = Depends(get_db)):
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    # Ленивая проверка активности: штрафы за неактивность (6 месяцев)
    # применяются точечным запросом при открытии профиля клуба — без
    # перебора всех спортсменов. См. app/services/club_rating.py.
    check_inactive_athletes(db)

    city_name = club.city.name if club.city else None
    athletes = (
        db.query(Athlete)
        .filter(Athlete.club_id == club.id, Athlete.is_hidden.is_(False))
        .order_by(Athlete.full_name)
        .all()
    )
    coaches = (
        db.query(Coach)
        .filter(Coach.club_id == club.id, Coach.is_hidden.is_(False))
        .order_by(Coach.full_name)
        .all()
    )

    return ClubDetailOut(
        id=club.id,
        name=club.name,
        logo_path=club.logo_path,
        description=club.description,
        address=club.address,
        city_name=city_name,
        founded_date=club.founded_date,
        rating_points=club.rating_points,
        athletes_count=len(athletes),
        coaches_count=len(coaches),
        athletes=[
            ClubMemberOut(id=a.id, full_name=a.full_name, photo_path=a.photo_path)
            for a in athletes
        ],
        coaches=[
            ClubMemberOut(id=c.id, full_name=c.full_name, photo_path=c.photo_path)
            for c in coaches
        ],
    )


@router.get("/{club_id}/rating", response_model=ClubRatingOut)
def get_club_rating_endpoint(club_id: int, db: Session = Depends(get_db)):
    """Текущий рейтинг клуба и журнал изменений (для профиля клуба).

    Перед чтением применяется ленивая проверка активности спортсменов
    клуба (штраф -5 за простой более 6 месяцев).
    """
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    check_inactive_athletes(db)

    rating = get_club_rating(db, club_id)
    history = get_club_rating_history(db, club_id)
    return ClubRatingOut(
        rating=rating,
        history=[
            ClubRatingHistoryItemOut(
                id=h.id,
                created_at=h.created_at,
                points=h.points,
                reason=h.reason,
                description=h.description,
                athlete_name=h.athlete.full_name if h.athlete else None,
                tournament_name=h.tournament.name if h.tournament else None,
            )
            for h in history
        ],
    )
