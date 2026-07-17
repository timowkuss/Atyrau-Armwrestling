from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.competitions import CompetitionParticipant
from app.db.models.geo import City
from app.db.models.statistics import AthleteStatistic
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.athletes import (
    AthleteAdminListOut,
    AthleteCreate,
    AthleteStatisticsAdminOut,
    AthleteStatisticsUpdate,
    AthleteUpdate,
)

router = APIRouter(prefix="/athletes", tags=["admin:athletes"])

WRITE_ROLES = ("super_admin", "admin")


@router.get("", response_model=list[AthleteAdminListOut])
def list_athletes_admin(
    name: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """В отличие от /public/athletes, включает и is_hidden=true —
    иначе скрытого спортсмена в админке было бы невозможно найти,
    чтобы снова сделать видимым."""
    query = (
        db.query(Athlete, Club.name.label("club_name"), Coach.full_name.label("coach_name"), City.name.label("city_name"))
        .outerjoin(Club, Athlete.club_id == Club.id)
        .outerjoin(Coach, Athlete.coach_id == Coach.id)
        .outerjoin(City, Athlete.city_id == City.id)
    )
    if name:
        query = query.filter(Athlete.full_name.ilike(f"%{name}%"))
    rows = query.order_by(Athlete.full_name).all()
    return [
        AthleteAdminListOut(
            id=athlete.id,
            full_name=athlete.full_name,
            birth_date=athlete.birth_date,
            gender=athlete.gender,
            club_name=club_name,
            coach_name=coach_name,
            city_name=city_name,
            rank=athlete.rank,
            photo_path=athlete.photo_path,
            is_hidden=athlete.is_hidden,
        )
        for athlete, club_name, coach_name, city_name in rows
    ]


@router.post("", status_code=201)
def create_athlete(
    payload: AthleteCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    athlete = Athlete(**payload.model_dump())
    db.add(athlete)
    db.flush()
    db.add(AthleteStatistic(athlete_id=athlete.id))
    db.commit()
    return {"id": athlete.id}


@router.patch("/{athlete_id}")
def update_athlete(
    athlete_id: int,
    payload: AthleteUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if athlete is None:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(athlete, field, value)
    db.commit()
    return {"status": "ok"}


@router.delete("/{athlete_id}")
def delete_athlete(
    athlete_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("super_admin")),
):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if athlete is None:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    has_participations = (
        db.query(CompetitionParticipant.id)
        .filter(CompetitionParticipant.athlete_id == athlete_id)
        .first()
        is not None
    )
    if has_participations:
        # athlete_id в competition_participants — NOT NULL + ondelete=RESTRICT,
        # жёсткое удаление физически невозможно, пока есть история участий
        # (см. app/db/models/competitions.py). Раньше этой проверки тут не
        # было — db.delete(athlete) на спортсмене с историей падал бы
        # необработанным IntegrityError (500) прямо в админке сайта.
        athlete.is_hidden = True
        db.commit()
        return {"status": "hidden", "reason": "has_participations"}

    db.delete(athlete)
    db.commit()
    return {"status": "deleted"}


@router.get("/{athlete_id}/statistics", response_model=AthleteStatisticsAdminOut)
def get_athlete_statistics(
    athlete_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    stats = db.query(AthleteStatistic).filter(AthleteStatistic.athlete_id == athlete_id).first()
    if stats is None:
        raise HTTPException(status_code=404, detail="Статистика спортсмена не найдена")
    return AthleteStatisticsAdminOut(
        total_competitions=stats.total_competitions,
        total_wins=stats.total_wins,
        total_losses=stats.total_losses,
        win_rate=stats.win_rate,
        left_hand_wins=stats.left_hand_wins,
        left_hand_losses=stats.left_hand_losses,
        right_hand_wins=stats.right_hand_wins,
        right_hand_losses=stats.right_hand_losses,
        gold_count=stats.gold_count,
        silver_count=stats.silver_count,
        bronze_count=stats.bronze_count,
        is_manual_override=stats.is_manual_override,
        overridden_by=stats.overridden_by,
        overridden_at=stats.overridden_at.isoformat() if stats.overridden_at else None,
    )


@router.patch("/{athlete_id}/statistics", response_model=AthleteStatisticsAdminOut)
def update_athlete_statistics(
    athlete_id: int,
    payload: AthleteStatisticsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Ручная правка статистики. Автоматически защищает изменённые значения
    от следующего автопересчёта (is_manual_override=True), см.
    ARCHITECTURE.md §3.4/§4.2 — например, если тестовый прогон или сетевой
    лаг на площадке задвоил победу/поражение."""
    stats = (
        db.query(AthleteStatistic).filter(AthleteStatistic.athlete_id == athlete_id).first()
    )
    if stats is None:
        raise HTTPException(status_code=404, detail="Статистика спортсмена не найдена")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Нет полей для изменения")

    for field, value in changes.items():
        setattr(stats, field, value)

    stats.is_manual_override = True
    stats.overridden_by = current_user.id
    stats.overridden_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(stats)

    return AthleteStatisticsAdminOut(
        total_competitions=stats.total_competitions,
        total_wins=stats.total_wins,
        total_losses=stats.total_losses,
        win_rate=stats.win_rate,
        left_hand_wins=stats.left_hand_wins,
        left_hand_losses=stats.left_hand_losses,
        right_hand_wins=stats.right_hand_wins,
        right_hand_losses=stats.right_hand_losses,
        gold_count=stats.gold_count,
        silver_count=stats.silver_count,
        bronze_count=stats.bronze_count,
        is_manual_override=stats.is_manual_override,
        overridden_by=stats.overridden_by,
        overridden_at=stats.overridden_at.isoformat() if stats.overridden_at else None,
    )


@router.post("/{athlete_id}/statistics/recalculate")
def recalculate_athlete_statistics(
    athlete_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Снимает is_manual_override. Сам пересчёт с нуля из истории турниров
    делает stats_engine.py (Этап 7, полноценный publish_pipeline) — здесь
    только снимается защита, чтобы следующая публикация турнира пересчитала
    этого спортсмена заново."""
    stats = (
        db.query(AthleteStatistic).filter(AthleteStatistic.athlete_id == athlete_id).first()
    )
    if stats is None:
        raise HTTPException(status_code=404, detail="Статистика спортсмена не найдена")

    stats.is_manual_override = False
    stats.overridden_by = None
    stats.overridden_at = None
    db.commit()
    return {"status": "override_cleared"}
