from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.competitions import CompetitionParticipant
from app.db.models.statistics import AthleteStatistic
from app.db.session import get_db
from app.schemas.sync import AthleteSearchResultItem, AthleteSyncCreate, AthleteSyncUpdate
from datetime import date, datetime

router = APIRouter(prefix="/athletes", tags=["sync:athletes"])

def _parse_birth_date(value: str) -> date:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value}")

def _normalize_gender(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {
        "M": "male", "M.": "male", "М": "male", "МУЖ": "male", "MALE": "male",
        "F": "female", "F.": "female", "Ж": "female", "ЖЕН": "female", "FEMALE": "female",
    }
    key = value.strip().upper()
    return mapping.get(key, value.strip().lower())


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


@router.get("/search", response_model=list[AthleteSearchResultItem])
def search_athletes(
    q: str,
    club: str | None = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Поиск спортсмена в центральной базе при регистрации участника в
    десктопе — организатор выбирает существующего или создаёт нового
    (см. ARCHITECTURE.md §5, шаг 1)."""
    query = db.query(Athlete, Club.name).outerjoin(Club, Athlete.club_id == Club.id)
    query = query.filter(Athlete.full_name.ilike(f"%{q}%"))
    if club:
        query = query.filter(Club.name.ilike(f"%{club}%"))

    rows = query.limit(20).all()
    return [
        AthleteSearchResultItem(
            id=a.id,
            full_name=a.full_name,
            club_name=club_name,
            gender=a.gender,
        )
        for a, club_name in rows
    ]


@router.post("", status_code=201)
def create_athlete(
    payload: AthleteSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    club_id = _find_or_create_club(db, payload.club_name)
    birth_date = _parse_birth_date(payload.birth_date) if payload.birth_date else None
    gender = _normalize_gender(payload.gender)


    athlete = Athlete(
        full_name=payload.full_name,
        gender=gender,
        birth_date=birth_date,
        club_id=club_id,
        rank=payload.rank,
        photo_path=payload.photo_path,
    )
    db.add(athlete)
    db.flush()
    db.add(AthleteStatistic(athlete_id=athlete.id))
    db.commit()
    return {"id": athlete.id}


@router.patch("/{athlete_id}")
def update_athlete(
    athlete_id: int,
    payload: AthleteSyncUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if athlete is None:
        return {"error": "not_found"}, 404

    data = payload.model_dump(exclude_unset=True)
    if "club_name" in data:
        athlete.club_id = _find_or_create_club(db, data.pop("club_name"))
    if "birth_date" in data and data["birth_date"]:
        data["birth_date"] = _parse_birth_date(data["birth_date"])
    if "gender" in data and data["gender"]:
        data["gender"] = _normalize_gender(data["gender"])

    for field, value in data.items():
        setattr(athlete, field, value)

    db.commit()
    return {"status": "ok"}


@router.delete("/{athlete_id}")
def delete_athlete(
    athlete_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Вызывается из десктопа (SyncApiClient.delete_athlete /
    sync_manager.on_athlete_deleted) при удалении спортсмена в реестре.
    Раньше этого роута здесь не было — desktop слал DELETE на
    /api/v1/sync/athletes/{id}, получал 405 Method Not Allowed и
    расценивал это как "нет сети", уводя операцию в офлайн-очередь
    НАВСЕГДА (она никогда не переставала бы проваливаться), что вдобавок
    блокировало вообще все последующие операции в очереди, т.к.
    flush_pending() останавливается на первой же неудаче. Подтверждено
    живым прогоном (create -> delete -> флаш очереди)."""
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
        # athlete_id в competition_participants NOT NULL + ondelete=RESTRICT —
        # жёсткое удаление физически невозможно, пока есть история участий
        # (см. app/db/models/competitions.py). Прячем карточку вместо этого —
        # ровно то, что обещает диалог удаления в десктопе: "записи участий
        # не удаляются".
        athlete.is_hidden = True
        db.commit()
        return {"status": "hidden", "reason": "has_participations"}

    db.delete(athlete)
    db.commit()
    return {"status": "deleted"}