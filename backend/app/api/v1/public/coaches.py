from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.geo import City
from app.db.session import get_db
from app.schemas.coaches import CoachDetailOut, CoachListOut
from app.schemas.common import Page

router = APIRouter(prefix="/coaches", tags=["public:coaches"])


@router.get("", response_model=Page[CoachListOut])
def list_coaches(
    name: str | None = None,
    club_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            Coach,
            Club.name.label("club_name"),
            City.name.label("city_name"),
            func.count(Athlete.id).label("athletes_count"),
        )
        .outerjoin(Club, Coach.club_id == Club.id)
        .outerjoin(City, Coach.city_id == City.id)
        .outerjoin(Athlete, (Athlete.coach_id == Coach.id) & (Athlete.is_hidden.is_(False)))
        .group_by(Coach.id, Club.name, City.name)
    )
    if name:
        query = query.filter(Coach.full_name.ilike(f"%{name}%"))
    if club_id is not None:
        query = query.filter(Coach.club_id == club_id)

    total = query.count()
    rows = (
        query.order_by(Coach.full_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        CoachListOut(
            id=coach.id,
            full_name=coach.full_name,
            photo_path=coach.photo_path,
            club_name=club_name,
            city_name=city_name,
            qualification=coach.qualification,
            birth_date=coach.birth_date,
            athletes_count=athletes_count,
        )
        for coach, club_name, city_name, athletes_count in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{coach_id}", response_model=CoachDetailOut)
def get_coach(coach_id: int, db: Session = Depends(get_db)):
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")

    club_name = coach.club.name if coach.club else None
    city_name = coach.city.name if coach.city else None
    athletes_count = db.query(Athlete).filter(Athlete.coach_id == coach.id, Athlete.is_hidden.is_(False)).count()

    return CoachDetailOut(
        id=coach.id,
        full_name=coach.full_name,
        photo_path=coach.photo_path,
        bio=coach.bio,
        club_name=club_name,
        city_name=city_name,
        qualification=coach.qualification,
        birth_date=coach.birth_date,
        athletes_count=athletes_count,
    )
