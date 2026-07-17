from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_desktop_sync
from app.db.models.categories import Category
from app.db.models.competitions import CompetitionParticipant
from app.db.models.matches import Match
from app.db.session import get_db

router = APIRouter(prefix="/categories", tags=["sync:categories"])


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_desktop_sync),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Каскад по category_id в миграции не подтверждён — чистим явно,
    # чтобы не оставить участников/матчи с category_id в никуда.
    db.query(CompetitionParticipant).filter(
        CompetitionParticipant.category_id == category_id
    ).delete(synchronize_session=False)
    db.query(Match).filter(Match.category_id == category_id).delete(synchronize_session=False)

    db.delete(category)
    db.commit()
    return {"status": "deleted"}