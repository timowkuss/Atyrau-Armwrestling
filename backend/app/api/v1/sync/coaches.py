from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.geo import City
from app.db.models.sync_tombstone import SyncTombstone
from app.db.session import get_db
from app.schemas.sync import (
    CoachChangeItem,
    CoachChangesOut,
    CoachSyncCreate,
    CoachSyncUpdate,
)
from app.services.cloudinary_photos import delete_cloudinary_photo

router = APIRouter(prefix="/coaches", tags=["sync:coaches"])


def _find_or_create_club(db: Session, club_name: str | None) -> int | None:
    if not club_name or not club_name.strip():
        return None
    name = club_name.strip()
    club = db.query(Club).filter(Club.name.ilike(name)).first()
    if club:
        return club.id
    club = Club(name=name)
    db.add(club)
    db.flush()
    return club.id


def _find_city_id(db: Session, city_name: str | None) -> int | None:
    """Город/район из десктопа — свободный текст, справочника cities там
    нет. В отличие от клубов, City требует обязательный region_id, поэтому
    город не создаём "вслепую" — только best-effort сопоставление по
    имени с уже существующим справочником (см. также location_name в
    CompetitionSyncCreate)."""
    if not city_name or not city_name.strip():
        return None
    city = db.query(City).filter(City.name.ilike(city_name.strip())).first()
    return city.id if city else None


def _parse_birth_date(value: str | None) -> date | None:
    """Десктоп шлёт дд.мм.гггг (как вводит организатор), возможен и ISO —
    та же логика, что в sync/athletes.py._parse_birth_date."""
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _find_existing_coach(db: Session, full_name: str) -> Coach | None:
    """Серверная защита от дублей — см. аналогичную функцию в
    sync/athletes.py. У тренера нет даты рождения для уточнения, поэтому
    сопоставляем строго по полному ФИО (без учёта регистра): реже
    встречаются полные тёзки среди тренеров, чем ложные пропуски дублей
    при десктоп-офлайн-очереди/повторной синхронизации без id_map."""
    return db.query(Coach).filter(Coach.full_name.ilike(full_name.strip())).first()


@router.get("/changes", response_model=CoachChangesOut)
def get_coach_changes(
    since: str | None = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Спрашивается десктопом периодически в фоне (см. sync/pull_sync.py):
    "что изменилось в карточках тренеров через админку с прошлого раза".
    Полная зеркальная копия GET /sync/athletes/changes — см. комментарии
    там же."""
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный формат since (ожидается ISO 8601)")

    server_time = datetime.now(timezone.utc)

    query = (
        db.query(Coach, Club.name, City.name)
        .outerjoin(Club, Coach.club_id == Club.id)
        .outerjoin(City, Coach.city_id == City.id)
    )
    if since_dt is not None:
        query = query.filter(Coach.updated_at > since_dt)
    rows = query.all()

    updated = [
        CoachChangeItem(
            id=c.id,
            full_name=c.full_name,
            club_name=club_name,
            photo_path=c.photo_path,
            bio=c.bio,
            first_name=c.first_name,
            last_name=c.last_name,
            birth_date=c.birth_date.isoformat() if c.birth_date else None,
            iin=c.iin,
            qualification=c.qualification,
            city_name=city_name,
            phone=c.phone,
            updated_at=c.updated_at.isoformat(),
        )
        for c, club_name, city_name in rows
    ]

    deleted: list[int] = []
    if since_dt is not None:
        tomb_rows = (
            db.query(SyncTombstone.entity_id)
            .filter(SyncTombstone.entity_type == "coach", SyncTombstone.deleted_at > since_dt)
            .all()
        )
        deleted = [r[0] for r in tomb_rows]

    return CoachChangesOut(
        server_time=server_time.isoformat(),
        updated=updated,
        deleted=deleted,
    )


@router.post("", status_code=201)
def create_coach(
    payload: CoachSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    club_id = _find_or_create_club(db, payload.club_name)
    city_id = _find_city_id(db, payload.city_name)
    birth_date = _parse_birth_date(payload.birth_date)

    existing = _find_existing_coach(db, payload.full_name)
    if existing is not None:
        # Тот же тренер уже есть на сервере — не плодим дубль, отдаём его
        # id (десктоп сохранит в id_map, как будто сам его создал), заодно
        # тихо доливаем пустые поля, не перетирая уже заполненные.
        if not existing.club_id and club_id:
            existing.club_id = club_id
        if not existing.city_id and city_id:
            existing.city_id = city_id
        if not existing.photo_path and payload.photo_path:
            existing.photo_path = payload.photo_path
        if not existing.bio and payload.bio:
            existing.bio = payload.bio
        if not existing.first_name and payload.first_name:
            existing.first_name = payload.first_name
        if not existing.last_name and payload.last_name:
            existing.last_name = payload.last_name
        if not existing.birth_date and birth_date:
            existing.birth_date = birth_date
        if not existing.iin and payload.iin:
            existing.iin = payload.iin
        if not existing.qualification and payload.qualification:
            existing.qualification = payload.qualification
        if not existing.phone and payload.phone:
            existing.phone = payload.phone
        db.commit()
        return {"id": existing.id, "status": "existing"}

    coach = Coach(
        full_name=payload.full_name,
        club_id=club_id,
        city_id=city_id,
        photo_path=payload.photo_path,
        bio=payload.bio,
        first_name=payload.first_name,
        last_name=payload.last_name,
        birth_date=birth_date,
        iin=payload.iin,
        qualification=payload.qualification,
        phone=payload.phone,
    )
    db.add(coach)
    db.commit()
    return {"id": coach.id, "status": "created"}


@router.patch("/{coach_id}")
def update_coach(
    coach_id: int,
    payload: CoachSyncUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if coach is None:
        return {"error": "not_found"}, 404

    old_photo_path = coach.photo_path
    data = payload.model_dump(exclude_unset=True)
    if "club_name" in data:
        coach.club_id = _find_or_create_club(db, data.pop("club_name"))
    if "city_name" in data:
        coach.city_id = _find_city_id(db, data.pop("city_name"))
    if "birth_date" in data:
        coach.birth_date = _parse_birth_date(data.pop("birth_date"))

    for field, value in data.items():
        if not hasattr(coach, field):
            continue
        setattr(coach, field, value)

    db.commit()

    # Старое фото удаляем только ПОСЛЕ успешного сохранения новой ссылки
    # (зеркально админскому эндпоинту) — десктоп при замене фото пушит
    # новый photo_path, а старый Cloudinary-файл больше не нужен.
    if old_photo_path and old_photo_path != coach.photo_path:
        delete_cloudinary_photo(old_photo_path)

    return {"status": "ok"}


@router.delete("/{coach_id}")
def delete_coach(
    coach_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """В отличие от athletes, у Coach нет прямой истории участий с
    ondelete=RESTRICT — Athlete.coach_id стоит SET NULL (см.
    app/db/models/athletes.py), поэтому жёсткое удаление тренера всегда
    безопасно: его спортсмены просто останутся без тренера, как и
    обещает диалог удаления в десктопе."""
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")

    photo_path = coach.photo_path
    db.add(SyncTombstone(entity_type="coach", entity_id=coach_id))
    db.delete(coach)
    db.commit()
    if photo_path:
        delete_cloudinary_photo(photo_path)
    return {"status": "deleted"}
