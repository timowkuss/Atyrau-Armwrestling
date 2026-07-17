from datetime import date, datetime, timezone
from app.api.v1.sync._common import parse_flexible_date


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.categories import Category
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.geo import City
from app.db.session import get_db
from app.schemas.sync import (
    CategorySyncCreate,
    CompetitionParticipantSyncCreate,
    CompetitionSyncCreate,
)

router = APIRouter(prefix="/competitions", tags=["sync:competitions"])


@router.post("", status_code=201)
def create_competition(
    payload: CompetitionSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Создаётся сразу при создании турнира в десктопе, статус=draft —
    на сайте ещё не публичен, но уже существует в единой БД
    (см. ARCHITECTURE.md §0/§5)."""
    city_id = None
    if payload.location_name and payload.location_name.strip():
        city = db.query(City).filter(City.name.ilike(payload.location_name.strip())).first()
        city_id = city.id if city else None

    competition = Competition(
        name=payload.name,
        date=parse_flexible_date(payload.date),
        location_city_id=city_id,
        status="draft",
    )
    db.add(competition)
    db.commit()
    db.refresh(competition)
    return {"id": competition.id, "matched_city": city_id is not None}


@router.post("/{competition_id}/categories", status_code=201)
def create_category(
    competition_id: int,
    payload: CategorySyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    category = Category(
        competition_id=competition_id,
        name=payload.name,
        hand=payload.hand,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return {"id": category.id}


@router.post("/{competition_id}/participants", status_code=201)
def create_participant(
    competition_id: int,
    payload: CompetitionParticipantSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    participant = CompetitionParticipant(
        competition_id=competition_id,
        athlete_id=payload.athlete_id,
        category_id=payload.category_id,
        weight_at_event=payload.weight_at_event,
        club_at_event=payload.club_at_event,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return {"id": participant.id}


@router.post("/{competition_id}/publish")
def publish_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Переключает статус draft -> published (см. ARCHITECTURE.md §5).
    Полный пересчёт статистики/рейтингов (stats_engine/ranking_engine) —
    Этап 7; здесь пока только смена статуса, этого достаточно, чтобы
    проверить сквозной поток десктоп -> центральная БД -> сайт."""
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    competition.status = "published"
    competition.published_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "published"}

@router.delete("/{competition_id}")
def delete_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Удаляет турнир из центральной БД. Категории, участники, матчи,
    результаты и медиа удаляются каскадно на уровне БД — все они
    ссылаются на competitions.id с ondelete='CASCADE'
    (см. alembic/versions/4d67b54f7d58_initial_schema.py)."""
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    db.delete(competition)
    db.commit()
    return {"status": "deleted"}
