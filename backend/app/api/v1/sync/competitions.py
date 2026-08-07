from datetime import date, datetime, timezone
from app.api.v1.sync._common import parse_flexible_date


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.categories import Category
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.dvoeborie_override import DvoeborieOverride
from app.db.models.geo import City
from app.db.session import get_db
from app.schemas.sync import (
    CategorySyncCreate,
    CompetitionParticipantSyncCreate,
    CompetitionSyncCreate,
)
from app.services.club_rating import check_inactive_athletes, finalize_competition

router = APIRouter(prefix="/competitions", tags=["sync:competitions"])


def _compute_phase(comp_date: date) -> str:
    """Вычисляет фазу турнира по дате: in_progress сегодня, completed если
    прошёл, published (ожидается) если в будущем."""
    today = date.today()
    if comp_date < today:
        return "completed"
    elif comp_date == today:
        return "in_progress"
    return "published"


@router.post("", status_code=201)
def create_competition(
    payload: CompetitionSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Создаётся сразу при создании турнира в десктопе.
    Автоматически публикуется с фазой based on дате."""
    city_id = None
    if payload.location_name and payload.location_name.strip():
        city = db.query(City).filter(City.name.ilike(payload.location_name.strip())).first()
        city_id = city.id if city else None

    comp_date = parse_flexible_date(payload.date)
    phase = _compute_phase(comp_date)

    competition = Competition(
        name=payload.name,
        date=comp_date,
        location_city_id=city_id,
        status=phase,
        published_at=datetime.now(timezone.utc),
        weight_tolerance=payload.weight_tolerance,
        bracket_system=payload.bracket_system,
        format_type=payload.format_type,
    )
    db.add(competition)
    db.commit()
    db.refresh(competition)
    return {"id": competition.id, "matched_city": city_id is not None, "status": phase}


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


class ParticipantSyncUpdate(BaseModel):
    weight_at_event: float | None = None
    club_at_event: str | None = None


@router.patch("/{competition_id}/participants/{participant_id}")
def update_participant(
    competition_id: int,
    participant_id: int,
    payload: ParticipantSyncUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Обновляет «снимок» участника после регистрации — в первую очередь
    вес после контрольного взвешивания (влияет на тай-брейк двоеборья)."""
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")
    participant = (
        db.query(CompetitionParticipant)
        .filter(
            CompetitionParticipant.id == participant_id,
            CompetitionParticipant.competition_id == competition_id,
        )
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    if payload.weight_at_event is not None:
        participant.weight_at_event = payload.weight_at_event
    if payload.club_at_event is not None:
        participant.club_at_event = payload.club_at_event
    db.commit()
    return {"status": "ok", "id": participant.id}


@router.post("/{competition_id}/publish")
def publish_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Переключает статус draft -> published."""
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    competition.status = "published"
    competition.published_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "published"}


class DvoeborieOverrideItem(BaseModel):
    category_id: int
    participant_id: int
    manual_rank: int


class DvoeborieOverridesSync(BaseModel):
    overrides: list[DvoeborieOverrideItem]


@router.post("/{competition_id}/dvoeborie-overrides", status_code=200)
def sync_dvoeborie_overrides(
    competition_id: int,
    payload: DvoeborieOverridesSync,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Заменяет ручные места двоеборья турнира (полный снимок из десктопа)."""
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    db.query(DvoeborieOverride).filter(
        DvoeborieOverride.competition_id == competition_id
    ).delete(synchronize_session=False)
    for item in payload.overrides:
        db.add(
            DvoeborieOverride(
                competition_id=competition_id,
                category_id=item.category_id,
                participant_id=item.participant_id,
                manual_rank=item.manual_rank,
            )
        )
    db.commit()
    return {"status": "ok", "count": len(payload.overrides)}


class StatusUpdate(BaseModel):
    status: str  # published | in_progress | completed


@router.patch("/{competition_id}/status")
def update_competition_status(
    competition_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Обновляет фазу турнира (published / in_progress / completed)."""
    if payload.status not in ("published", "in_progress", "completed"):
        raise HTTPException(status_code=400, detail="Недопустимый статус")

    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    competition.status = payload.status
    if payload.status == "published" and not competition.published_at:
        competition.published_at = datetime.now(timezone.utc)
    db.commit()

    if payload.status == "completed":
        # Турнир завершён: применяем штрафы за неактивность и начисляем
        # клубам рейтинг по итогам (места 1-3 и первое участие). Повторный
        # вызов идемпотентен — двойных начислений не будет.
        check_inactive_athletes(db)
        finalize_competition(db, competition)

    return {"status": competition.status}

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
