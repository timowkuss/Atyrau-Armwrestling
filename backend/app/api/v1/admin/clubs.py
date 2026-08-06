from fastapi import APIRouter, Depends, HTTPException
from datetime import date
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.athletes import Athlete
from app.db.models.clubs import Club, find_club_by_name
from app.db.models.coaches import Coach
from app.db.models.geo import City
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.clubs import (
    ClubAdminDetailOut,
    ClubAdminListOut,
    ClubCreate,
    ClubMemberOut,
    ClubMembersAdd,
    ClubUpdate,
)
from app.services.club_rating import apply_athlete_removed
from app.services.cloudinary_photos import delete_cloudinary_photo

router = APIRouter(prefix="/clubs", tags=["admin:clubs"])

WRITE_ROLES = ("super_admin", "admin")


@router.get("", response_model=list[ClubAdminListOut])
def list_clubs_admin(
    name: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Полный листинг клубов для админки (в отличие от публичного, с
    описанием и city_id — нужны для формы редактирования)."""
    query = (
        db.query(
            Club,
            City.name.label("city_name"),
            func.count(func.distinct(Athlete.id)).label("athletes_count"),
            func.count(func.distinct(Coach.id)).label("coaches_count"),
        )
        .outerjoin(City, Club.city_id == City.id)
        .outerjoin(Athlete, Athlete.club_id == Club.id)
        .outerjoin(Coach, Coach.club_id == Club.id)
        .group_by(Club.id, City.name)
        .order_by(Club.name)
    )
    if name:
        query = query.filter(Club.name.ilike(f"%{name}%"))
    rows = query.all()
    return [
        ClubAdminListOut(
            id=club.id,
            name=club.name,
            logo_path=club.logo_path,
            description=club.description,
            address=club.address,
            phone=club.phone,
            city_id=club.city_id,
            city_name=city_name,
            founded_date=club.founded_date,
            rating_points=club.rating_points,
            athletes_count=athletes_count,
            coaches_count=coaches_count,
        )
        for club, city_name, athletes_count, coaches_count in rows
    ]


@router.get("/{club_id}", response_model=ClubAdminDetailOut)
def get_club_admin(
    club_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Детали клуба для админки + списки участников (спортсмены и тренеры),
    которых можно добавлять/убирать со страницы клуба."""
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    athletes = (
        db.query(Athlete)
        .filter(Athlete.club_id == club.id)
        .order_by(Athlete.full_name)
        .all()
    )
    coaches = (
        db.query(Coach)
        .filter(Coach.club_id == club.id)
        .order_by(Coach.full_name)
        .all()
    )
    city_name = club.city.name if club.city else None

    return ClubAdminDetailOut(
        id=club.id,
        name=club.name,
        logo_path=club.logo_path,
        description=club.description,
        address=club.address,
        phone=club.phone,
        city_id=club.city_id,
        city_name=city_name,
        founded_date=club.founded_date,
        rating_points=club.rating_points,
        athletes_count=len(athletes),
        coaches_count=len(coaches),
        athletes=[ClubMemberOut(id=a.id, full_name=a.full_name, photo_path=a.photo_path) for a in athletes],
        coaches=[ClubMemberOut(id=c.id, full_name=c.full_name, photo_path=c.photo_path) for c in coaches],
    )


@router.post("", status_code=201)
def create_club(
    payload: ClubCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Название клуба обязательно")
    if not payload.city_id:
        raise HTTPException(status_code=400, detail="Укажите город/область клуба")
    # Дубль по имени (без учёта регистра): «Атырау», «АТырау» и «атырау» — это
    # один клуб, создавать его второй раз нельзя (см. b1c2d3e4f5a6 — уникальный
    # индекс на lower(name)). В отличие от sync (там ретрай офлайн-очереди
    # идемпотентен), в админке повторное имя — ошибка, а не возврат существующего.
    existing = find_club_by_name(db, payload.name)
    if existing is not None:
        raise HTTPException(status_code=400, detail="Клуб с таким названием уже существует")
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
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None and not data["name"].strip():
        raise HTTPException(status_code=400, detail="Название клуба обязательно")
    # Переименование в имя другого существующего клуба — запрещено
    # (та же логика дедупа, что и при создании).
    if "name" in data and data["name"] is not None:
        existing = find_club_by_name(db, data["name"])
        if existing is not None and existing.id != club.id:
            raise HTTPException(status_code=400, detail="Клуб с таким названием уже существует")
    old_logo_path = club.logo_path
    for field, value in data.items():
        setattr(club, field, value)
    db.commit()

    # Старое лого удаляем только ПОСЛЕ успешного сохранения новой ссылки
    # (зеркально sync/clubs.py) — заменённый Cloudinary-файл больше не нужен.
    if old_logo_path and old_logo_path != club.logo_path:
        delete_cloudinary_photo(old_logo_path)

    return {"status": "ok"}


@router.post("/{club_id}/members")
def add_club_members(
    club_id: int,
    payload: ClubMembersAdd,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Добавляет спортсменов и/или тренеров в клуб — присваивает им
    club_id. Тот, кто уже состоял в другом клубе, автоматически переводится
    в этот (старому клубу начисляется штраф -10 за удаление спортсмена)."""
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    if payload.athlete_ids:
        athletes = (
            db.query(Athlete)
            .filter(Athlete.id.in_(payload.athlete_ids))
            .all()
        )
        for athlete in athletes:
            old_club_id = athlete.club_id
            if old_club_id is not None and old_club_id != club.id:
                # перевод из другого клуба = удаление из него (штраф -10)
                apply_athlete_removed(db, athlete.id, old_club_id)
            athlete.club_id = club.id
            # вступление в (новый) клуб: с этого момента спортсмен — член
            # клуба, но неактивен до первого участия в турнире
            if athlete.join_club_date is None or old_club_id != club.id:
                athlete.join_club_date = date.today()
            athlete.club_active = False
            athlete.next_inactive_date = None
    if payload.coach_ids:
        db.query(Coach).filter(Coach.id.in_(payload.coach_ids)).update(
            {"club_id": club.id}, synchronize_session=False
        )
    db.commit()
    return {"status": "ok"}


@router.post("/{club_id}/members/remove")
def remove_club_members(
    club_id: int,
    payload: ClubMembersAdd,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Убирает спортсменов/тренеров из клуба — обнуляет их club_id.
    Клубу начисляется штраф -10 за каждого удалённого спортсмена."""
    club = db.query(Club).filter(Club.id == club_id).first()
    if club is None:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    if payload.athlete_ids:
        athletes = (
            db.query(Athlete)
            .filter(Athlete.id.in_(payload.athlete_ids), Athlete.club_id == club.id)
            .all()
        )
        for athlete in athletes:
            apply_athlete_removed(db, athlete.id, club.id)
            athlete.club_id = None
            athlete.club_active = False
            athlete.join_club_date = None
            athlete.next_inactive_date = None
    if payload.coach_ids:
        db.query(Coach).filter(
            Coach.id.in_(payload.coach_ids), Coach.club_id == club.id
        ).update({"club_id": None}, synchronize_session=False)
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
    logo_path = club.logo_path
    db.delete(club)
    db.commit()
    if logo_path:
        delete_cloudinary_photo(logo_path)
    return {"status": "deleted"}
