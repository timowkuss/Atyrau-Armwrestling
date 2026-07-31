from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.clubs import Club
from app.db.models.geo import City
from app.db.session import get_db
from app.schemas.sync import ClubSyncCreate, ClubSyncItem, ClubSyncUpdate

router = APIRouter(prefix="/clubs", tags=["sync:clubs"])


def _find_city_id(db: Session, city_name: str | None) -> int | None:
    if not city_name or not city_name.strip():
        return None
    city = db.query(City).filter(City.name.ilike(city_name.strip())).first()
    return city.id if city else None


@router.get("", response_model=list[ClubSyncItem])
def list_clubs(
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Полный список клубов для десктопа (см. sync/pull_sync.py). Клубов
    немного — отдаём все, десктоп сам решает, что у него уже есть."""
    rows = (
        db.query(Club, City.name)
        .outerjoin(City, Club.city_id == City.id)
        .order_by(Club.name)
        .all()
    )
    return [
        ClubSyncItem(
            id=club.id,
            name=club.name,
            city_name=city_name,
            founded_year=club.founded_year,
            logo_path=club.logo_path,
        )
        for club, city_name in rows
    ]


@router.post("", status_code=201)
def create_club(
    payload: ClubSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Название клуба обязательно")
    club = Club(
        name=payload.name.strip(),
        city_id=_find_city_id(db, payload.city_name),
        founded_year=payload.founded_year,
        logo_path=payload.logo_path,
    )
    db.add(club)
    db.commit()
    return {"id": club.id}


@router.patch("/{club_id}")
def update_club(
    club_id: int,
    payload: ClubSyncUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        return {"error": "not_found"}, 404

    data = payload.model_dump(exclude_unset=True)
    if "city_name" in data:
        club.city_id = _find_city_id(db, data.pop("city_name"))

    for field, value in data.items():
        if not hasattr(club, field):
            continue
        setattr(club, field, value)

    db.commit()
    return {"status": "ok"}


@router.delete("/{club_id}")
def delete_club(
    club_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    db.delete(club)
    db.commit()
    return {"status": "deleted"}
