from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.coaches import Coach
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.coaches import CoachCreate, CoachUpdate

router = APIRouter(prefix="/coaches", tags=["admin:coaches"])

WRITE_ROLES = ("super_admin", "admin")


@router.post("", status_code=201)
def create_coach(
    payload: CoachCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    coach = Coach(**payload.model_dump())
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
    for field, value in payload.model_dump(exclude_unset=True).items():
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
    db.delete(coach)
    db.commit()
    return {"status": "deleted"}
