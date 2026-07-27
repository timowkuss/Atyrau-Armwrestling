from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.sync_tombstone import SyncTombstone
from app.db.session import get_db
from app.schemas.sync import (
    CoachChangeItem,
    CoachChangesOut,
    CoachSyncCreate,
    CoachSyncUpdate,
)

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

    query = db.query(Coach, Club.name).outerjoin(Club, Coach.club_id == Club.id)
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
            updated_at=c.updated_at.isoformat(),
        )
        for c, club_name in rows
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

    existing = _find_existing_coach(db, payload.full_name)
    if existing is not None:
        # Тот же тренер уже есть на сервере — не плодим дубль, отдаём его
        # id (десктоп сохранит в id_map, как будто сам его создал), заодно
        # тихо доливаем пустые поля, не перетирая уже заполненные.
        if not existing.club_id and club_id:
            existing.club_id = club_id
        if not existing.photo_path and payload.photo_path:
            existing.photo_path = payload.photo_path
        if not existing.bio and payload.bio:
            existing.bio = payload.bio
        db.commit()
        return {"id": existing.id, "status": "existing"}

    coach = Coach(
        full_name=payload.full_name,
        club_id=club_id,
        photo_path=payload.photo_path,
        bio=payload.bio,
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

    data = payload.model_dump(exclude_unset=True)
    if "club_name" in data:
        coach.club_id = _find_or_create_club(db, data.pop("club_name"))

    for field, value in data.items():
        setattr(coach, field, value)

    db.commit()
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

    db.add(SyncTombstone(entity_type="coach", entity_id=coach_id))
    db.delete(coach)
    db.commit()
    return {"status": "deleted"}
