from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.api.v1.sync._common import parse_flexible_date
from app.db.models.clubs import Club, find_club_by_name
from app.db.models.geo import City
from app.db.session import get_db
from app.schemas.sync import ClubSyncCreate, ClubSyncItem, ClubSyncUpdate
from app.services.cloudinary_photos import delete_cloudinary_photo

router = APIRouter(prefix="/clubs", tags=["sync:clubs"])


def _find_city_id(db: Session, city_name: str | None) -> int | None:
    if not city_name or not city_name.strip():
        return None
    city = db.query(City).filter(City.name.ilike(city_name.strip())).first()
    return city.id if city else None


def _parse_founded_date(value: str | None):
    if not value:
        return None
    return parse_flexible_date(value)


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
            address=club.address,
            city_name=city_name,
            founded_date=club.founded_date.isoformat() if club.founded_date else None,
            logo_path=club.logo_path,
            phone=club.phone,
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
    # Дедуп по имени (без учёта регистра): повторная отправка одного и того же
    # клуба (ретрай офлайн-очереди десктопа при потерянном ответе, импорт)
    # НЕ плодит дубли — возвращаем существующий клуб. См. миграцию
    # b1c2d3e4f5a6 (уникальный индекс на lower(name)).
    existing = find_club_by_name(db, payload.name)
    if existing is not None:
        return {"id": existing.id, "duplicate": True}
    club = Club(
        name=payload.name.strip(),
        address=payload.address,
        city_id=_find_city_id(db, payload.city_name),
        founded_date=_parse_founded_date(payload.founded_date),
        logo_path=payload.logo_path,
        phone=payload.phone,
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
        raise HTTPException(status_code=404, detail="Клуб не найден")

    data = payload.model_dump(exclude_unset=True)
    if "city_name" in data:
        club.city_id = _find_city_id(db, data.pop("city_name"))
    if "founded_date" in data:
        data["founded_date"] = _parse_founded_date(data["founded_date"])

    old_logo_path = club.logo_path
    for field, value in data.items():
        if not hasattr(club, field):
            continue
        setattr(club, field, value)

    db.commit()

    # Старое лого удаляем только ПОСЛЕ успешного сохранения новой ссылки
    # (зеркально admin/clubs.py и sync/athletes.py, coaches.py) — десктоп
    # при замене лого пушит новый logo_path, старый Cloudinary-файл больше
    # не нужен.
    if old_logo_path and old_logo_path != club.logo_path:
        delete_cloudinary_photo(old_logo_path)

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

    logo_path = club.logo_path
    db.delete(club)
    db.commit()
    if logo_path:
        delete_cloudinary_photo(logo_path)
    return {"status": "deleted"}
