from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.geo import City
from app.db.models.sync_tombstone import SyncTombstone
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.coaches import (
    CoachAdminDetailOut,
    CoachAdminListOut,
    CoachCreate,
    CoachUpdate,
)
from app.schemas.common import Page

router = APIRouter(prefix="/coaches", tags=["admin:coaches"])

WRITE_ROLES = ("super_admin", "admin")


@router.get("", response_model=Page[CoachAdminListOut])
def list_coaches_admin(
    page: int = 1,
    page_size: int = 200,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES, "editor")),
):
    """Листинг с ИИН — только для админки (публичный /public/coaches его не
    отдаёт, см. схемы coaches.py)."""
    query = (
        db.query(
            Coach,
            Club.name.label("club_name"),
            City.name.label("city_name"),
            func.count(Athlete.id).label("athletes_count"),
        )
        .outerjoin(Club, Coach.club_id == Club.id)
        .outerjoin(City, Coach.city_id == City.id)
        .outerjoin(Athlete, Athlete.coach_id == Coach.id)
        .group_by(Coach.id, Club.name, City.name)
        .order_by(Coach.full_name)
    )
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [
        CoachAdminListOut(
            id=coach.id,
            full_name=coach.full_name,
            photo_path=coach.photo_path,
            club_name=club_name,
            city_name=city_name,
            qualification=coach.qualification,
            birth_date=coach.birth_date,
            iin=coach.iin,
            athletes_count=athletes_count,
        )
        for coach, club_name, city_name, athletes_count in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{coach_id}", response_model=CoachAdminDetailOut)
def get_coach_admin(
    coach_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES, "editor")),
):
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")
    athletes_count = db.query(Athlete).filter(Athlete.coach_id == coach.id).count()
    return CoachAdminDetailOut(
        id=coach.id,
        full_name=coach.full_name,
        photo_path=coach.photo_path,
        bio=coach.bio,
        club_name=coach.club.name if coach.club else None,
        city_name=coach.city.name if coach.city else None,
        qualification=coach.qualification,
        birth_date=coach.birth_date,
        iin=coach.iin,
        athletes_count=athletes_count,
    )


@router.post("", status_code=201)
def create_coach(
    payload: CoachCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    if payload.iin and db.query(Coach).filter(Coach.iin == payload.iin).first():
        raise HTTPException(status_code=400, detail="Тренер с таким ИИН уже существует")

    data = payload.model_dump()
    full_name = f"{data.pop('last_name')} {data.pop('first_name')}".strip()
    coach = Coach(full_name=full_name, **data)
    db.add(coach)
    db.commit()
    db.refresh(coach)
    return {"id": coach.id}


@router.patch("/{coach_id}")
def update_coach(
    coach_id: int,
    payload: CoachUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")

    data = payload.model_dump(exclude_unset=True)

    if data.get("iin") and (
        db.query(Coach)
        .filter(Coach.iin == data["iin"], Coach.id != coach_id)
        .first()
    ):
        raise HTTPException(status_code=400, detail="Тренер с таким ИИН уже существует")

    first_name = data.pop("first_name", None)
    last_name = data.pop("last_name", None)
    if first_name is not None:
        coach.first_name = first_name
    if last_name is not None:
        coach.last_name = last_name
    if first_name is not None or last_name is not None:
        coach.full_name = f"{coach.last_name or ''} {coach.first_name or ''}".strip()

    for field, value in data.items():
        setattr(coach, field, value)
    db.commit()
    return {"status": "ok"}


@router.delete("/{coach_id}")
def delete_coach(
    coach_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("super_admin")),
):
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")
    db.add(SyncTombstone(entity_type="coach", entity_id=coach_id))
    db.delete(coach)
    db.commit()
    return {"status": "deleted"}
