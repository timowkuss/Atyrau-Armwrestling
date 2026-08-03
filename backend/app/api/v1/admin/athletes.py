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
from app.db.models.sync_tombstone import SyncTombstone
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.athletes import (
    AthleteAdminDetailOut,
    AthleteAdminListOut,
    AthleteCreate,
    AthleteStatisticsAdminOut,
    AthleteStatisticsUpdate,
    AthleteUpdate,
)
from app.services.cloudinary_photos import delete_cloudinary_photo
from app.services.club_rating import apply_athlete_removed
from app.services.elo_engine import elo_combined

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
            iin=athlete.iin,
            phone=athlete.phone,
        )
        for athlete, club_name, coach_name, city_name in rows
    ]


@router.post("", status_code=201)
def create_athlete(
    payload: AthleteCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    athlete = Athlete(**payload.model_dump(exclude={"iin", "phone"}))
    if payload.iin:
        athlete.iin = payload.iin
    if payload.phone:
        athlete.phone = payload.phone
    if athlete.club_id is not None:
        # вступление в клуб: фиксируем дату; активность появится после
        # первого участия в турнире (см. app/services/club_rating.py)
        athlete.join_club_date = datetime.now(timezone.utc).date()
        athlete.club_active = False
    if payload.iin and db.query(Athlete).filter(Athlete.iin == payload.iin).first():
        raise HTTPException(status_code=400, detail="Спортсмен с таким ИИН уже существует")
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

    data = payload.model_dump(exclude_unset=True)

    # ── пустой ИИН = стёрт: храним NULL, а не '' (иначе unique-constraint
    # посчитает двух спортсменов с пустым ИИН дубликатом) ───────────────
    if "iin" in data and not data["iin"]:
        data["iin"] = None

    # ── ИИН уникален для всех спортсменов (в т.ч. скрытых) ──────────
    if data.get("iin") and (
        db.query(Athlete).filter(Athlete.iin == data["iin"], Athlete.id != athlete_id).first()
    ):
        raise HTTPException(status_code=400, detail="Спортсмен с таким ИИН уже существует")

    # ── смена клуба / выход из клуба: рейтинг клубов ───────────
    # - выход из клуба (club_id → None)          : штраф -10 старому клубу
    # - перевод (club_id A → B)                  : штраф -10 A, вступление в B
    # - вступление (None → B)                    : фиксация даты вступления
    if "club_id" in data:
        old_club_id = athlete.club_id
        new_club_id = data["club_id"]
        if old_club_id != new_club_id:
            if old_club_id is not None:
                apply_athlete_removed(db, athlete.id, old_club_id)
                if new_club_id is None:
                    athlete.club_active = False
                    athlete.join_club_date = None
                    athlete.next_inactive_date = None
            if new_club_id is not None:
                athlete.join_club_date = datetime.now(timezone.utc).date()
                athlete.club_active = False
                athlete.next_inactive_date = None

    # ── фото: та же логика, что и в sync/athletes.py update_athlete —
    # старое фото в Cloudinary удаляем только ПОСЛЕ успешного сохранения
    # новой ссылки, и только если оно реально поменялось.
    old_photo_path = athlete.photo_path
    new_photo_path = data.get("photo_path", old_photo_path)
    photo_changed = "photo_path" in data and new_photo_path != old_photo_path

    for field, value in data.items():
        if not hasattr(athlete, field):
            continue
        setattr(athlete, field, value)
    db.commit()

    if photo_changed and old_photo_path:
        delete_cloudinary_photo(old_photo_path)

    return {"status": "ok"}


@router.delete("/{athlete_id}/photo")
def delete_athlete_photo(
    athlete_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Отдельная кнопка "Удалить фото" в админке — та же логика, что
    PATCH с photo_path=null в update_athlete выше, просто удобнее
    вызывать с фронта одной кнопкой."""
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if athlete is None:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    old_photo_path = athlete.photo_path
    if not old_photo_path:
        return {"status": "ok"}

    athlete.photo_path = None
    db.commit()

    delete_cloudinary_photo(old_photo_path)
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
        # необработанным IntegrityError (500) прямо в админке сайта. Фото
        # НЕ трогаем — карточка может снова стать видимой.
        athlete.is_hidden = True
        db.commit()
        return {"status": "hidden", "reason": "has_participations"}

    old_photo_path = athlete.photo_path

    # Tombstone для обратной синхронизации (сайт -> десктоп): без него
    # десктоп никогда бы не узнал об удалении из админки спортсмена без
    # истории участий (карточка просто исчезла бы из changes-выдачи).
    db.add(SyncTombstone(entity_type="athlete", entity_id=athlete_id))
    db.delete(athlete)
    db.commit()

    if old_photo_path:
        delete_cloudinary_photo(old_photo_path)

    return {"status": "deleted"}


@router.get("/{athlete_id}", response_model=AthleteAdminDetailOut)
def get_athlete_admin(
    athlete_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    athlete = db.get(Athlete, athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    club_name = athlete.club.name if athlete.club else None
    coach_name = athlete.coach.full_name if athlete.coach else None
    city_name = athlete.city.name if athlete.city else None
    region_name = athlete.city.region.name if athlete.city and athlete.city.region else None
    country_name = athlete.city.region.country.name if athlete.city and athlete.city.region and athlete.city.region.country else None
    return AthleteAdminDetailOut(
        id=athlete.id,
        full_name=athlete.full_name,
        birth_date=athlete.birth_date,
        gender=athlete.gender,
        club_name=club_name,
        coach_name=coach_name,
        city_name=city_name,
        region_name=region_name,
        country_name=country_name,
        rank=athlete.rank,
        photo_path=athlete.photo_path,
        bio=athlete.bio,
        iin=athlete.iin,
        phone=athlete.phone,
    )


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
        elo_left=stats.elo_left,
        elo_right=stats.elo_right,
        elo_combined=elo_combined(stats.elo_left, stats.elo_right),
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
        elo_left=stats.elo_left,
        elo_right=stats.elo_right,
        elo_combined=elo_combined(stats.elo_left, stats.elo_right),
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
