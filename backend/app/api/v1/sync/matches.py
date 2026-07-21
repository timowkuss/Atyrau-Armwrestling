from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.matches import Match
from app.db.session import get_db
from app.schemas.sync import MatchSyncCreate, MatchSyncUpdate
from app.services.elo_engine import apply_match_result

router = APIRouter(prefix="/matches", tags=["sync:matches"])


@router.post("", status_code=201)
def create_match(
    payload: MatchSyncCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    """Пишется сразу по ходу сетки в десктопе, а не пакетом в конце
    (см. ARCHITECTURE.md §5, шаг 4)."""
    match = Match(competition_id=_competition_id_of(db, payload), **payload.model_dump())
    db.add(match)
    db.flush()
    # На практике winner_id на создании почти всегда пуст (матч только
    # появился в сетке), но если это BYE-проброс с сразу известным
    # победителем — apply_match_result сам отфильтрует BYE и выйдет.
    apply_match_result(db, match)
    db.commit()
    db.refresh(match)
    return {"id": match.id}


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

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(match, field, value)

    # Здесь приходит победитель по ходу турнира (или его исправление) —
    # это и есть точка пересчёта рейтинга, см. app/services/elo_engine.py.
    apply_match_result(db, match)

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
