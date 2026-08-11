from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.services.cloudinary_photos import delete_cloudinary_photo

router = APIRouter(prefix="/coaches", tags=["admin:coaches"])

WRITE_ROLES = ("super_admin", "admin")


def _release_students(db: Session, coach_id: int) -> None:
    """Тренер удалён или скрыт — все его ученики автоматически остаются
    без тренера (coach_id → NULL), ровно как обещает диалог удаления.
    При жёстком удалении FK (ondelete=SET NULL) справился бы и сам, но
    при скрытии (is_hidden) тренер остаётся в БД — нужен явный UPDATE.
    Скрытие идемпотентно: повторный вызов ничего не ломает."""
    db.query(Athlete).filter(Athlete.coach_id == coach_id).update(
        {Athlete.coach_id: None}, synchronize_session=False
    )


@router.get("", response_model=Page[CoachAdminListOut])
def list_coaches_admin(
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
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
            first_name=coach.first_name,
            last_name=coach.last_name,
            phone=coach.phone,
            athletes_count=athletes_count,
            is_hidden=coach.is_hidden,
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
        first_name=coach.first_name,
        last_name=coach.last_name,
        phone=coach.phone,
        athletes_count=athletes_count,
        is_hidden=coach.is_hidden,
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

    # ── пустой ИИН = стёрт: храним NULL, а не '' (иначе unique-constraint
    # посчитает двух тренеров с пустым ИИН дубликатом) ──────────────────
    if "iin" in data and not data["iin"]:
        data["iin"] = None

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

    # ── фото: та же логика, что и в sync/coaches.py update_coach — старое
    # фото в Cloudinary удаляем только ПОСЛЕ успешного сохранения новой
    # ссылки, и только если оно реально поменялось.
    old_photo_path = coach.photo_path
    new_photo_path = data.get("photo_path", old_photo_path)
    photo_changed = "photo_path" in data and new_photo_path != old_photo_path

    for field, value in data.items():
        setattr(coach, field, value)

    # ── скрытие тренера: каскад ──────────────────────────────────
    # Как и у спортсменов: скрытая карточка покидает клуб (club_id=NULL)
    # и отпускает всех своих учеников (coach_id=NULL у спортсменов).
    # Возврат видимости ("Показать") ничего не восстанавливает — тренера
    # нужно заново привязать к клубу/ученикам, как в десктопе.
    if data.get("is_hidden"):
        _release_students(db, coach.id)
        coach.club_id = None

    db.commit()

    if photo_changed and old_photo_path:
        delete_cloudinary_photo(old_photo_path)

    return {"status": "ok"}


@router.delete("/{coach_id}/photo")
def delete_coach_photo(
    coach_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Отдельная кнопка "Удалить фото" в админке — без необходимости
    гонять весь объект тренера ради одного поля. Делает то же самое, что
    PATCH с photo_path=null (см. update_coach выше), просто удобнее
    вызывать с фронта."""
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")

    old_photo_path = coach.photo_path
    if not old_photo_path:
        return {"status": "ok"}

    coach.photo_path = None
    db.commit()

    delete_cloudinary_photo(old_photo_path)
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

    old_photo_path = coach.photo_path

    # Сначала отпускаем учеников (явно, не полагаясь на FK SET NULL) —
    # иначе между UPDATE/DELETE при отключённых внешних ключах часть
    # спортсменов может остаться ссылаться на несуществующего тренера.
    _release_students(db, coach_id)

    db.add(SyncTombstone(entity_type="coach", entity_id=coach_id))
    db.delete(coach)
    db.commit()

    if old_photo_path:
        delete_cloudinary_photo(old_photo_path)

    return {"status": "deleted"}
