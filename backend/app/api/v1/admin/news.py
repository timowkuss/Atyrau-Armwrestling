from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.news import News
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.news import NewsCreate, NewsDetailOut, NewsListOut, NewsUpdate

router = APIRouter(prefix="/news", tags=["admin:news"])

WRITE_ROLES = ("super_admin", "admin", "editor")


@router.get("", response_model=list[NewsListOut])
def list_news(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Список для админки — и черновики, и опубликованные (в отличие от
    гипотетического публичного эндпоинта, которого пока нет)."""
    items = db.query(News).order_by(News.created_at.desc()).all()
    return [NewsListOut.model_validate(n, from_attributes=True) for n in items]


@router.get("/{news_id}", response_model=NewsDetailOut)
def get_news(
    news_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    news = db.query(News).filter(News.id == news_id).first()
    if news is None:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    return NewsDetailOut.model_validate(news, from_attributes=True)


@router.post("", status_code=201)
def create_news(
    payload: NewsCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    if db.query(News).filter(News.slug == payload.slug).first():
        raise HTTPException(status_code=409, detail="Новость с таким slug уже существует")

    news = News(
        **payload.model_dump(),
        author_user_id=current_user.id,
        published_at=datetime.now(timezone.utc) if payload.is_published else None,
    )
    db.add(news)
    db.commit()
    db.refresh(news)
    return {"id": news.id}


@router.patch("/{news_id}")
def update_news(
    news_id: int,
    payload: NewsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    news = db.query(News).filter(News.id == news_id).first()
    if news is None:
        raise HTTPException(status_code=404, detail="Новость не найдена")

    changes = payload.model_dump(exclude_unset=True)
    was_published = news.is_published
    for field, value in changes.items():
        setattr(news, field, value)
    if "is_published" in changes and changes["is_published"] and not was_published:
        news.published_at = datetime.now(timezone.utc)

    db.commit()
    return {"status": "ok"}


@router.delete("/{news_id}")
def delete_news(
    news_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    news = db.query(News).filter(News.id == news_id).first()
    if news is None:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    db.delete(news)
    db.commit()
    return {"status": "deleted"}
