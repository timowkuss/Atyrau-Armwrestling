from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.clubs import Club
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.geo import City
from app.db.models.matches import Match
from app.db.models.results import Result
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.competitions import (
    BracketMatchOut,
    CategoryOut,
    CompetitionDetailOut,
    CompetitionListOut,
    EliminatedOut,
    QueuePairOut,
    ResultOut,
    TableQueueOut,
)

router = APIRouter(prefix="/competitions", tags=["public:competitions"])


@router.get("", response_model=Page[CompetitionListOut])
def list_competitions(
    year: int | None = None,
    status: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            Competition,
            City.name.label("city_name"),
            func.count(CompetitionParticipant.id).label("participants_count"),
        )
        .outerjoin(City, Competition.location_city_id == City.id)
        .outerjoin(
            CompetitionParticipant,
            CompetitionParticipant.competition_id == Competition.id,
        )
        .group_by(Competition.id, City.name)
    )
    if status:
        query = query.filter(Competition.status == status)
    else:
        query = query.filter(Competition.status != "draft")
    if year is not None:
        query = query.filter(func.date_part("year", Competition.date) == year)

    total = query.count()
    rows = (
        query.order_by(Competition.date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        CompetitionListOut(
            id=competition.id,
            name=competition.name,
            date=competition.date,
            location_city_name=city_name,
            organizer=competition.organizer,
            status=competition.status,
            participants_count=participants_count,
        )
        for competition, city_name, participants_count in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{competition_id}", response_model=CompetitionDetailOut)
def get_competition(competition_id: int, db: Session = Depends(get_db)):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    city_name = (
        db.get(City, competition.location_city_id).name
        if competition.location_city_id
        else None
    )
    participants_count = (
        db.query(CompetitionParticipant)
        .filter(CompetitionParticipant.competition_id == competition.id)
        .count()
    )
    categories = [
        CategoryOut(id=c.id, name=c.name, hand=c.hand) for c in competition.categories
    ]

    return CompetitionDetailOut(
        id=competition.id,
        name=competition.name,
        date=competition.date,
        location_city_name=city_name,
        organizer=competition.organizer,
        description=competition.description,
        poster_path=competition.poster_path,
        regulations_doc_path=competition.regulations_doc_path,
        status=competition.status,
        participants_count=participants_count,
        weight_tolerance=competition.weight_tolerance,
        bracket_system=competition.bracket_system,
        format_type=competition.format_type,
        categories=categories,
    )


@router.get("/{competition_id}/results", response_model=list[ResultOut])
def get_competition_results(competition_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(
            Category.name.label("category_name"),
            Result.place,
            Result.medal,
            Athlete.id.label("athlete_id"),
            Athlete.full_name.label("athlete_name"),
            Club.name.label("club_name"),
        )
        .join(Category, Result.category_id == Category.id)
        .join(
            CompetitionParticipant,
            Result.competition_participant_id == CompetitionParticipant.id,
        )
        .join(Athlete, CompetitionParticipant.athlete_id == Athlete.id)
        .outerjoin(Club, Athlete.club_id == Club.id)
        .filter(Result.competition_id == competition_id)
        .order_by(Category.name, Result.place)
        .all()
    )
    return [
        ResultOut(
            category_name=r.category_name,
            place=r.place,
            medal=r.medal,
            athlete_id=r.athlete_id,
            athlete_name=r.athlete_name,
            club_name=r.club_name,
        )
        for r in rows
    ]


@router.get("/{competition_id}/bracket", response_model=list[BracketMatchOut])
def get_competition_bracket(competition_id: int, db: Session = Depends(get_db)):
    matches = (
        db.query(Match, Category)
        .join(Category, Match.category_id == Category.id)
        .filter(Match.competition_id == competition_id)
        .order_by(Category.name, Match.bracket, Match.stage, Match.match_order)
        .all()
    )

    # Раньше здесь на каждый матч уходило до 3 отдельных db.get(...) плюс
    # ленивая подгрузка match.athlete под капотом каждого — на сетку из
    # ~14 матчей это ~80+ запросов к БД на один открытие страницы. Берём
    # разом всех нужных участников одним запросом с joinedload(athlete).
    participant_ids: set[int] = set()
    for match, _ in matches:
        for pid in (match.p1_id, match.p2_id, match.winner_id):
            if pid:
                participant_ids.add(pid)

    participants_by_id: dict[int, CompetitionParticipant] = {}
    if participant_ids:
        rows = (
            db.query(CompetitionParticipant)
            .options(joinedload(CompetitionParticipant.athlete))
            .filter(CompetitionParticipant.id.in_(participant_ids))
            .all()
        )
        participants_by_id = {p.id: p for p in rows}

    items = []
    for match, category in matches:
        p1 = participants_by_id.get(match.p1_id) if match.p1_id else None
        p2 = participants_by_id.get(match.p2_id) if match.p2_id else None
        winner = participants_by_id.get(match.winner_id) if match.winner_id else None
        items.append(
            BracketMatchOut(
                id=match.id,
                category_name=category.name,
                hand=match.hand,
                bracket=match.bracket,
                round_name=match.round_name,
                match_order=match.match_order,
                stage=match.stage,
                p1_name=p1.athlete.full_name if p1 else None,
                p2_name=p2.athlete.full_name if p2 else None,
                winner_name=winner.athlete.full_name if winner else None,
                status=match.status,
            )
        )
    return items


@router.get("/{competition_id}/queue", response_model=list[TableQueueOut])
def get_competition_queue(competition_id: int, db: Session = Depends(get_db)):
    """Живая очередь пар по столам: текущий поединок + до 3 следующих.
    Внизу каждого стола — выбывшие спортсмены с занятыми местами.

    Матч попадает в выдачу, если у него проставлен table_number и он ещё
    не сыгран (status pending/waiting) — даже если пока известен только
    один участник (второй ещё не вышел из предыдущего раунда). Для
    неизвестной стороны показываем "Неизвестно" вместо того, чтобы
    полностью скрывать пару: зрителю полезно видеть, кто уже точно
    попал в следующий бой, не дожидаясь, пока определится соперник.
    Полностью пустые матчи (оба участника ещё не определены) в выдачу
    не попадают — по ним просто нечего показать.
    Столы без table_number (старые записи, ещё не досинкан десктоп) в
    выдачу не попадают.
    """
    UNKNOWN = "Неизвестно"

    # -------------------- 1. Определяем систему: DE или SE --------------------
    has_loser_bracket = (
        db.query(Match.id)
        .filter(
            Match.competition_id == competition_id,
            Match.bracket == "losers",
        )
        .limit(1)
        .first()
        is not None
    )
    max_losses = 2 if has_loser_bracket else 1

    # ---- 2. Все матчи с table_number (нужны для полного списка столов) ----
    all_table_matches = (
        db.query(Match, Category)
        .join(Category, Match.category_id == Category.id)
        .filter(
            Match.competition_id == competition_id,
            Match.table_number.isnot(None),
        )
        .order_by(Match.table_number, Match.stage, Match.id)
        .all()
    )

    # ---- 3. Только pending/waiting для очереди ----
    pending_matches: list[tuple[Match, Category]] = []
    for match, cat in all_table_matches:
        if match.status in ("pending", "waiting"):
            pending_matches.append((match, cat))

    # Батчим участников (N+1 prevention)
    participant_ids: set[int] = set()
    for match, _ in pending_matches:
        if match.p1_id is not None:
            participant_ids.add(match.p1_id)
        if match.p2_id is not None:
            participant_ids.add(match.p2_id)

    participants_by_id: dict[int, CompetitionParticipant] = {}
    if participant_ids:
        rows = (
            db.query(CompetitionParticipant)
            .options(joinedload(CompetitionParticipant.athlete))
            .filter(CompetitionParticipant.id.in_(participant_ids))
            .all()
        )
        participants_by_id = {p.id: p for p in rows}

    # Группируем пары по столам (пропускаем где оба — "Неизвестно")
    tables: dict[int, list[QueuePairOut]] = {}
    for match, category in pending_matches:
        p1 = participants_by_id.get(match.p1_id) if match.p1_id is not None else None
        p2 = participants_by_id.get(match.p2_id) if match.p2_id is not None else None
        p1_name = p1.athlete.full_name if p1 else UNKNOWN
        p2_name = p2.athlete.full_name if p2 else UNKNOWN
        if p1_name == UNKNOWN and p2_name == UNKNOWN:
            continue
        pair = QueuePairOut(
            match_id=match.id,
            category_name=category.name,
            hand=match.hand,
            round_name=match.round_name,
            p1_name=p1_name,
            p2_name=p2_name,
        )
        tables.setdefault(match.table_number, []).append(pair)

    # Сначала пары где известны ОБА участника, потом с "Неизвестно"
    for tnum in tables:
        tables[tnum].sort(key=lambda p: (
            0 if UNKNOWN not in (p.p1_name, p.p2_name) else 1,
        ))

    # ---- 4. Строим map table_number → (category_name, hand, category_id) ----
    table_meta: dict[int, tuple[str, str, int]] = {}
    for match, category in all_table_matches:
        table_meta[match.table_number] = (category.name, match.hand, match.category_id)

    # ---- 5. Вычисляем выбывших спортсменов ----
    done_matches = (
        db.query(Match)
        .filter(
            Match.competition_id == competition_id,
            Match.status == "done",
            Match.winner_id.isnot(None),
        )
        .all()
    )

    # Группируем сыгранные матчи по (категория, рука)
    cat_hand_done: dict[tuple[int, str], list[Match]] = {}
    for m in done_matches:
        cat_hand_done.setdefault((m.category_id, m.hand), []).append(m)

    # Все участники для разрешения имён (один запрос)
    all_participants = (
        db.query(CompetitionParticipant)
        .options(joinedload(CompetitionParticipant.athlete))
        .filter(CompetitionParticipant.competition_id == competition_id)
        .all()
    )
    all_participants_by_id: dict[int, CompetitionParticipant] = {p.id: p for p in all_participants}

    # Выбывшие по ключу (category_id, hand)
    eliminated_by_key: dict[tuple[int, str], list[EliminatedOut]] = {}

    for (cat_id, hand), cat_matches in cat_hand_done.items():
        stats: dict[int, dict] = {}

        def _ensure(pid):
            if pid is not None and pid not in stats:
                stats[pid] = {"pid": pid, "wins": 0, "losses": 0, "last_loss_stage": -1}

        for m in cat_matches:
            _ensure(m.p1_id)
            _ensure(m.p2_id)
            if m.winner_id:
                winner = m.winner_id
                loser = m.p2_id if winner == m.p1_id else m.p1_id
                _ensure(winner)
                stats[winner]["wins"] += 1
                if loser:
                    _ensure(loser)
                    stats[loser]["losses"] += 1
                    if m.stage > stats[loser]["last_loss_stage"]:
                        stats[loser]["last_loss_stage"] = m.stage

        if not stats:
            continue

        # Завершён ли ГФ
        gf_done = any(m.bracket == "final" and m.status == "done" for m in cat_matches)
        champion = None
        if gf_done:
            gf_matches = [m for m in cat_matches if m.bracket == "final"]
            last_gf = max(gf_matches, key=lambda m: m.id)
            champion = last_gf.winner_id

        # Сортируем: чемпион первым, потом по числу поражений, затем по победам
        ordered = sorted(
            stats.values(),
            key=lambda s: (
                0 if s["pid"] == champion else 1,
                s["losses"],
                -s["wins"],
            )
        )

        eliminated = []
        for i, s in enumerate(ordered):
            is_eliminated = gf_done or s["losses"] >= max_losses
            if is_eliminated:
                p = all_participants_by_id.get(s["pid"])
                name = p.athlete.full_name if p else UNKNOWN
                eliminated.append(EliminatedOut(
                    athlete_name=name,
                    place=i + 1,
                    wins=s["wins"],
                    losses=s["losses"],
                ))

        eliminated_by_key[(cat_id, hand)] = eliminated

    # ---- 6. Собираем ответ по всем столам ----
    response: list[TableQueueOut] = []
    for tnum in sorted(table_meta):
        cat_name, hand, cat_id = table_meta[tnum]
        pairs = tables.get(tnum, [])
        elim = eliminated_by_key.get((cat_id, hand), [])
        response.append(TableQueueOut(
            table_number=tnum,
            category_name=cat_name,
            hand=hand,
            current=pairs[0] if pairs else None,
            next=pairs[1:4],
            eliminated=elim,
        ))

    return response


@router.get("/{competition_id}/participants")
def get_competition_participants(competition_id: int, db: Session = Depends(get_db)):
    """Список участников соревнования, сгруппированный по категориям."""
    from pydantic import BaseModel

    class ParticipantOut(BaseModel):
        athlete_id: int
        athlete_name: str
        category_name: str

    rows = (
        db.query(
            CompetitionParticipant.athlete_id,
            Athlete.full_name.label("athlete_name"),
            Category.name.label("category_name"),
        )
        .join(Athlete, CompetitionParticipant.athlete_id == Athlete.id)
        .join(Category, CompetitionParticipant.category_id == Category.id)
        .filter(CompetitionParticipant.competition_id == competition_id)
        .order_by(Category.name, Athlete.full_name)
        .all()
    )
    return [
        ParticipantOut(
            athlete_id=r.athlete_id,
            athlete_name=r.athlete_name,
            category_name=r.category_name,
        )
        for r in rows
    ]
