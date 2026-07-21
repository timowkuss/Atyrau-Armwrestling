from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

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
    ParticipantOut,
    QueuePairOut,
    ResultOut,
    TableQueueOut,
)
from app.schemas.media import PhotoOut

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
    """Только просмотр сетки — редактирование запрещено на сайте
    (см. ARCHITECTURE.md §6: сетка/результаты — только из десктопа)."""
    matches = (
        db.query(Match, Category)
        .join(Category, Match.category_id == Category.id)
        .filter(Match.competition_id == competition_id)
        .order_by(Category.name, Match.bracket, Match.match_order)
        .all()
    )

    items = []
    for match, category in matches:
        p1 = db.get(CompetitionParticipant, match.p1_id) if match.p1_id else None
        p2 = db.get(CompetitionParticipant, match.p2_id) if match.p2_id else None
        winner = db.get(CompetitionParticipant, match.winner_id) if match.winner_id else None
        items.append(
            BracketMatchOut(
                id=match.id,
                category_name=category.name,
                bracket=match.bracket,
                round_name=match.round_name,
                match_order=match.match_order,
                p1_name=p1.athlete.full_name if p1 else None,
                p2_name=p2.athlete.full_name if p2 else None,
                winner_name=winner.athlete.full_name if winner else None,
                status=match.status,
            )
        )
    return items


@router.get("/{competition_id}/queue", response_model=list[TableQueueOut])
def get_competition_queue(competition_id: int, db: Session = Depends(get_db)):
    """Живая очередь пар по столам: текущий поединок + до 4 следующих.

    Пара считается определившейся, только когда у матча заполнены оба
    p1_id/p2_id (см. get_current_and_next_match в десктопе — та же логика).
    Столы без table_number (старые записи, ещё не досинкан десктоп) в
    выдачу не попадают.
    """
    matches = (
        db.query(Match, Category)
        .join(Category, Match.category_id == Category.id)
        .filter(
            Match.competition_id == competition_id,
            Match.status == "pending",
            Match.p1_id.isnot(None),
            Match.p2_id.isnot(None),
            Match.table_number.isnot(None),
        )
        .order_by(Match.table_number, Match.stage, Match.id)
        .all()
    )

    tables: dict[int, list[QueuePairOut]] = {}
    for match, category in matches:
        p1 = db.get(CompetitionParticipant, match.p1_id)
        p2 = db.get(CompetitionParticipant, match.p2_id)
        if p1 is None or p2 is None:
            continue
        pair = QueuePairOut(
            match_id=match.id,
            category_name=category.name,
            round_name=match.round_name,
            p1_name=p1.athlete.full_name,
            p2_name=p2.athlete.full_name,
        )
        tables.setdefault(match.table_number, []).append(pair)

    return [
        TableQueueOut(table_number=tnum, current=pairs[0], next=pairs[1:4])
        for tnum, pairs in sorted(tables.items())
    ]


@router.get("/{competition_id}/participants", response_model=list[ParticipantOut])
def get_competition_participants(competition_id: int, db: Session = Depends(get_db)):
    """Список участников соревнования, сгруппированный по категориям."""
    rows = (
        db.query(
            CompetitionParticipant,
            Category.name.label("category_name"),
            Category.hand.label("hand"),
        )
        .join(Category, CompetitionParticipant.category_id == Category.id)
        .join(Athlete, CompetitionParticipant.athlete_id == Athlete.id)
        .filter(CompetitionParticipant.competition_id == competition_id)
        .order_by(Category.name, Athlete.full_name)
        .all()
    )
    return [
        ParticipantOut(
            athlete_id=cp.athlete_id,
            athlete_name=cp.athlete.full_name,
            category_name=cat_name,
            hand=hand,
            weight_at_event=cp.weight_at_event,
            club_at_event=cp.club_at_event,
        )
        for cp, cat_name, hand in rows
    ]


@router.get("/{competition_id}/photos", response_model=list[PhotoOut])
def competition_photos(competition_id: int, db: Session = Depends(get_db)):
    from app.db.models.media import Photo
    photos = db.query(Photo).filter(Photo.competition_id == competition_id).order_by(Photo.uploaded_at.desc()).all()
    return [PhotoOut.model_validate(p, from_attributes=True) for p in photos]
