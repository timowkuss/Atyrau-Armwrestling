from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.competitions import CompetitionParticipant
from app.db.models.statistics import AthleteStatistic
from app.db.models.sync_tombstone import SyncTombstone
from app.db.session import get_db
from app.schemas.sync import (
    AthleteChangeItem,
    AthleteChangesOut,
    AthleteSearchResultItem,
    AthleteSyncCreate,
    AthleteSyncUpdate,
)
from app.api.v1.sync._common import normalize_full_name
from app.services.club_rating import apply_athlete_removed, mark_joined
from app.services.cloudinary_photos import delete_cloudinary_photo
from datetime import date, datetime, timezone

router = APIRouter(prefix="/athletes", tags=["sync:athletes"])

def _detach_from_club_and_coach(db: Session, athlete: Athlete) -> None:
    """Скрытие/удаление спортсмена: выход из клуба (штраф -10 рейтингу,
    активность сбрасывается) и от тренера. Зеркально admin/athletes.py —
    иначе скрытие с десктопа и скрытие с сайта вели бы себя по-разному."""
    if athlete.club_id is not None:
        apply_athlete_removed(db, athlete.id, athlete.club_id)
        athlete.club_id = None
        athlete.club_active = False
        athlete.join_club_date = None
        athlete.next_inactive_date = None
    athlete.coach_id = None

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


def _find_coach(db: Session, coach_name: str | None) -> int | None:
    if not coach_name or not coach_name.strip():
        return None
    name = coach_name.strip()
    coach = db.query(Coach).filter(Coach.full_name.ilike(name)).first()
    return coach.id if coach else None


def _find_existing_athlete(db: Session, full_name: str, birth_date: date | None) -> Athlete | None:
    """Серверная проверка дублей при синхронизации.

    Раньше защита от дублей держалась только на локальной id_map
    десктоп-приложения: если эту карту потерять (переустановка, второй
    компьютер, ручная синхронизация с нуля), один и тот же спортсмен мог
    улететь на сервер второй раз под новым id. Здесь — вторая линия
    защиты уже на центральной базе.

    Сопоставляем по нормализованному ФИО (без учёта регистра и порядка
    слов) + дате рождения — этого достаточно, чтобы не путать полных
    тёзок, и в то же время не сработает ложно на "Иванов Иван" без даты
    рождения. Если дата рождения не пришла — не пытаемся сопоставлять по
    одному имени, слишком велик риск склеить разных людей."""
    if not birth_date:
        return None
    key = normalize_full_name(full_name)
    if not key:
        return None
    return next(
        (
            a
            for a in db.query(Athlete).filter(Athlete.birth_date == birth_date).all()
            if normalize_full_name(a.full_name) == key
        ),
        None,
    )


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


@router.get("/changes", response_model=AthleteChangesOut)
def get_athlete_changes(
    since: str | None = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Спрашивается десктопом периодически в фоне (см. sync/pull_sync.py):
    "что изменилось в карточках спортсменов через админку с прошлого
    раза". since — ISO-таймстамп из предыдущего ответа этого же
    эндпоинта (поле server_time); при первом запросе не передаётся —
    тогда отдаём вообще все карточки (десктоп сам решит, что из этого
    уже есть локально, по своей id_map).

    server_time берём с САМОГО СЕРВЕРА (а не время десктопа), чтобы не
    зависеть от рассинхронизации часов клиента — десктоп просто
    сохраняет то, что мы вернули, и присылает обратно в следующий раз.
    """
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный формат since (ожидается ISO 8601)")

    server_time = datetime.now(timezone.utc)

    query = db.query(Athlete, Club.name, Coach.full_name).outerjoin(Club, Athlete.club_id == Club.id).outerjoin(Coach, Athlete.coach_id == Coach.id)
    if since_dt is not None:
        query = query.filter(Athlete.updated_at > since_dt)
    rows = query.all()

    updated = [
        AthleteChangeItem(
            id=a.id,
            full_name=a.full_name,
            club_name=club_name,
            gender=a.gender,
            birth_date=a.birth_date.isoformat() if a.birth_date else None,
            rank=a.rank,
            photo_path=a.photo_path,
            coach_name=coach_name,
            iin=a.iin,
            phone=a.phone,
            is_hidden=a.is_hidden,
            updated_at=a.updated_at.isoformat(),
        )
        for a, club_name, coach_name in rows
    ]

    deleted: list[int] = []
    if since_dt is not None:
        tomb_rows = (
            db.query(SyncTombstone.entity_id)
            .filter(SyncTombstone.entity_type == "athlete", SyncTombstone.deleted_at > since_dt)
            .all()
        )
        deleted = [r[0] for r in tomb_rows]

    return AthleteChangesOut(
        server_time=server_time.isoformat(),
        updated=updated,
        deleted=deleted,
    )


@router.post("", status_code=201)
def create_athlete(
    payload: AthleteSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    club_id = _find_or_create_club(db, payload.club_name)
    coach_id = _find_coach(db, payload.coach_name)
    birth_date = _parse_birth_date(payload.birth_date) if payload.birth_date else None
    gender = _normalize_gender(payload.gender)

    existing = _find_existing_athlete(db, payload.full_name, birth_date)

    # ── ИИН уникален для всех спортсменов (в т.ч. скрытых) ──────────
    if payload.iin:
        dup = db.query(Athlete).filter(Athlete.iin == payload.iin).first()
        if dup is not None and (existing is None or dup.id != existing.id):
            raise HTTPException(
                status_code=409,
                detail="Спортсмен с таким ИИН уже существует",
            )

    if existing is not None:
        # Уже есть спортсмен с таким же ФИО и датой рождения — не создаём
        # дубль, отдаём его id (десктоп сохранит его в своей id_map, как
        # будто сам его создал). Заодно тихо доливаем те поля, которые у
        # существующей карточки ещё пустые — но НЕ перетираем то, что там
        # уже есть, чтобы не потерять ранее внесённые данные.
        if not existing.club_id and club_id:
            existing.club_id = club_id
            existing.join_club_date = datetime.now(timezone.utc).date()
            existing.club_active = False
        if not existing.gender and gender:
            existing.gender = gender
        if not existing.rank and payload.rank:
            existing.rank = payload.rank
        if not existing.photo_path and payload.photo_path:
            existing.photo_path = payload.photo_path
        if not existing.coach_id and coach_id:
            existing.coach_id = coach_id
        db.commit()
        return {"id": existing.id, "status": "existing"}

    athlete = Athlete(
        full_name=payload.full_name,
        gender=gender,
        birth_date=birth_date,
        club_id=club_id,
        coach_id=coach_id,
        rank=payload.rank,
        photo_path=payload.photo_path,
        iin=payload.iin,
        phone=payload.phone,
    )
    if club_id is not None:
        athlete.join_club_date = datetime.now(timezone.utc).date()
        athlete.club_active = False
    db.add(athlete)
    db.flush()
    db.add(AthleteStatistic(athlete_id=athlete.id))
    db.commit()
    return {"id": athlete.id, "status": "created"}


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

    old_club_id = athlete.club_id
    old_photo_path = athlete.photo_path
    data = payload.model_dump(exclude_unset=True)

    # ── ИИН уникален для всех спортсменов (в т.ч. скрытых) ──────────
    if data.get("iin"):
        dup = db.query(Athlete).filter(
            Athlete.iin == data["iin"], Athlete.id != athlete_id
        ).first()
        if dup is not None:
            raise HTTPException(
                status_code=409,
                detail="Спортсмен с таким ИИН уже существует",
            )

    if "club_name" in data:
        athlete.club_id = _find_or_create_club(db, data.pop("club_name"))
    if "coach_name" in data:
        athlete.coach_id = _find_coach(db, data.pop("coach_name"))
    if "iin" in data:
        athlete.iin = data.pop("iin")
    if "phone" in data:
        athlete.phone = data.pop("phone")
    if "birth_date" in data and data["birth_date"]:
        data["birth_date"] = _parse_birth_date(data["birth_date"])
    if "gender" in data and data["gender"]:
        data["gender"] = _normalize_gender(data["gender"])

    # ── смена клуба: рейтинг клубов (штраф старому, вступление в новый) ──
    if athlete.club_id != old_club_id:
        if old_club_id is not None:
            apply_athlete_removed(db, athlete.id, old_club_id)
            if athlete.club_id is None:
                athlete.club_active = False
                athlete.join_club_date = None
                athlete.next_inactive_date = None
        if athlete.club_id is not None:
            mark_joined(db, athlete.id)
            athlete.club_active = False
            athlete.next_inactive_date = None

    for field, value in data.items():
        setattr(athlete, field, value)

    # ── скрытие спортсмена: каскад (см. admin/athletes.py) ────────
    if data.get("is_hidden"):
        _detach_from_club_and_coach(db, athlete)

    db.commit()

    # Старое фото удаляем только ПОСЛЕ успешного сохранения новой ссылки
    # (зеркально админскому эндпоинту) — десктоп при замене фото пушит
    # новый photo_path, а старый Cloudinary-файл больше не нужен.
    if old_photo_path and old_photo_path != athlete.photo_path:
        delete_cloudinary_photo(old_photo_path)

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
        _detach_from_club_and_coach(db, athlete)
        athlete.is_hidden = True
        db.commit()
        return {"status": "hidden", "reason": "has_participations"}

    photo_path = athlete.photo_path
    if athlete.club_id is not None:
        apply_athlete_removed(db, athlete.id, athlete.club_id)
    db.add(SyncTombstone(entity_type="athlete", entity_id=athlete_id))
    db.delete(athlete)
    db.commit()
    if photo_path:
        delete_cloudinary_photo(photo_path)
    return {"status": "deleted"}