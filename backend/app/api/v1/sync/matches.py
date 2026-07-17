from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.matches import Match
from app.db.session import get_db
from app.schemas.sync import MatchSyncCreate, MatchSyncUpdate

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
    db.commit()
    return {"status": "ok"}
