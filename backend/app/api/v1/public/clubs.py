from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.geo import City
from app.db.session import get_db
from app.schemas.clubs import ClubDetailOut, ClubListOut
from app.schemas.common import Page

router = APIRouter(prefix="/clubs", tags=["public:clubs"])


@router.get("", response_model=Page[ClubListOut])
def list_clubs(
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
        .outerjoin(Athlete, Athlete.club_id == Club.id)
        .group_by(Club.id, City.name)
    )
    if city_id is not None:
        query = query.filter(Club.city_id == city_id)

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

    city_name = club.city.name if club.city else None
    athletes_count = db.query(Athlete).filter(Athlete.club_id == club.id).count()
    coaches_count = db.query(Coach).filter(Coach.club_id == club.id).count()

    return ClubDetailOut(
        id=club.id,
        name=club.name,
        logo_path=club.logo_path,
        description=club.description,
        city_name=city_name,
        founded_year=club.founded_year,
        rating_points=club.rating_points,
        athletes_count=athletes_count,
        coaches_count=coaches_count,
    )
