from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.competitions import CompetitionParticipant
from app.db.models.matches import Match
from app.db.session import get_db
from app.schemas.sync import MatchSyncBatchCreate, MatchSyncCreate, MatchSyncUpdate
from app.services.elo_engine import apply_match_result
from app.services.results_engine import finalize_category_results

router = APIRouter(prefix="/matches", tags=["sync:matches"])


def _validate_participants_belong(
    db: Session, category_id: int, participant_ids: set[int | None]
) -> None:
    """Участники матча (p1/p2/winner) обязаны быть участниками той же
    категории: иначе клиент может «вписать» в чужой матч участника
    другой категории/турнира и исказить elo/итоги. Значения None (ещё
    не определившаяся сторона) пропускаются."""
    ids = {pid for pid in participant_ids if pid is not None}
    if not ids:
        return
    found = {
        pid
        for (pid,) in db.query(CompetitionParticipant.id)
        .filter(
            CompetitionParticipant.id.in_(ids),
            CompetitionParticipant.category_id == category_id,
        )
        .all()
    }
    if found != ids:
        raise HTTPException(
            status_code=422,
            detail=(
                "Участники матча не принадлежат категории: "
                f"{sorted(ids - found)}"
            ),
        )


@router.post("", status_code=201)
def create_match(
    payload: MatchSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Пишется сразу по ходу сетки в десктопе, а не пакетом в конце
    (см. ARCHITECTURE.md §5, шаг 4)."""
    _validate_participants_belong(
        db, payload.category_id, {payload.p1_id, payload.p2_id, payload.winner_id}
    )
    match = Match(competition_id=_competition_id_of(db, payload), **payload.model_dump())
    db.add(match)
    db.flush()
    # На практике winner_id на создании почти всегда пуст (матч только
    # появился в сетке), но если это BYE-проброс с сразу известным
    # победителем — apply_match_result сам отфильтрует BYE и выйдет.
    apply_match_result(db, match)
    # Если этим матчем сетка категории+руки внезапно уже доигралась
    # (крайний случай — bye до самого финала), посчитаем места сразу же.
    finalize_category_results(db, match.category_id, match.hand)
    db.commit()
    db.refresh(match)
    return {"id": match.id}


@router.post("/batch", status_code=201)
def create_matches_batch(
    payload: MatchSyncBatchCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Пакетное создание матчей сетки одним запросом (десктоп при
    первичной синхронизации турнира: 4000-6000 отдельных POST → 1).

    Семантика идентична одиночному create_match: после каждого матча
    применяется elo (apply_match_result сам отфильтрует BYE) и по
    каждой затронутой категории+руке пересчитываются итоговые места.
    Разница лишь в том, что коммит — один на весь пакет."""
    created: list[Match] = []
    affected: set[tuple[int, str]] = set()
    for item in payload.matches:
        _validate_participants_belong(
            db, item.category_id, {item.p1_id, item.p2_id, item.winner_id}
        )
        match = Match(
            competition_id=_competition_id_of(db, item), **item.model_dump()
        )
        db.add(match)
        db.flush()
        created.append(match)
        apply_match_result(db, match)
        affected.add((match.category_id, match.hand))

    for category_id, hand in affected:
        finalize_category_results(db, category_id, hand)

    db.commit()
    return {"ids": [m.id for m in created]}


def _competition_id_of(db: Session, payload: MatchSyncCreate) -> int:
    from app.db.models.categories import Category

    category = db.query(Category).filter(Category.id == payload.category_id).first()
    if category is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    return category.competition_id


@router.patch("/{match_id}")
def update_match(
    match_id: int,
    payload: MatchSyncUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if match is None:
        raise HTTPException(status_code=404, detail="Матч не найден")

    # Обновление участников/победителя — только в рамках категории матча.
    if payload.model_dump(exclude_unset=True).get("winner_id") is not None or any(
        payload.model_dump(exclude_unset=True).get(f) is not None
        for f in ("p1_id", "p2_id")
    ):
        _validate_participants_belong(
            db, match.category_id, {payload.p1_id, payload.p2_id, payload.winner_id}
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        if not hasattr(match, field):
            continue
        setattr(match, field, value)

    # Здесь приходит победитель по ходу турнира (или его исправление) —
    # это и есть точка пересчёта рейтинга, см. app/services/elo_engine.py.
    apply_match_result(db, match)
    # Та же точка — самое надёжное место пересчитать итоговые места
    # категории: сработает и когда доигран обычный финал, и когда
    # сыграна переигровка гранд-финала, и при исправлении результата
    # задним числом (пересчёт идемпотентный, см. results_engine.py).
    finalize_category_results(db, match.category_id, match.hand)

    db.commit()
    return {"status": "ok"}


@router.delete("")
def delete_matches(
    category_id: int,
    hand: str,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Вызывается десктопом при сбросе/пересоздании сетки категории
    (см. Database.clear_matches). Без этого старые матчи остаются
    висеть на сервере и дают дубли пар в живой очереди
    (/public/competitions/{id}/queue)."""
    db.query(Match).filter(
        Match.category_id == category_id, Match.hand == hand
    ).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok"}
