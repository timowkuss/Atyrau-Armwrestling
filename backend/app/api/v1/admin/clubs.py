from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.clubs import Club
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.clubs import ClubCreate, ClubUpdate

router = APIRouter(prefix="/clubs", tags=["admin:clubs"])

WRITE_ROLES = ("super_admin", "admin")


@router.post("", status_code=201)
def create_club(
    payload: ClubCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    club = Club(**payload.model_dump())
    db.add(club)
    db.commit()
    db.refresh(club)
    return {"id": club.id}


@router.patch("/{club_id}")
def update_club(
    club_id: int,
    payload: ClubUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(club, field, value)
    db.commit()
    return {"status": "ok"}


@router.delete("/{club_id}")
def delete_club(
    club_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("super_admin")),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    db.delete(club)
    db.commit()
    return {"status": "deleted"}
