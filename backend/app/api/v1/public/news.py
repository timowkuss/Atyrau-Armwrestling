from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models.news import News
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.news import NewsDetailOut, NewsListOut

router = APIRouter(prefix="/news", tags=["public:news"])


@router.get("", response_model=Page[NewsListOut])
def list_news(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    query = db.query(News).filter(News.is_published.is_(True)).order_by(News.published_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=[NewsListOut.model_validate(n, from_attributes=True) for n in items], total=total, page=page, page_size=page_size)


@router.get("/{slug}", response_model=NewsDetailOut)
def get_news(slug: str, db: Session = Depends(get_db)):
    news = db.query(News).filter(News.slug == slug, News.is_published.is_(True)).first()
    if news is None:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    return NewsDetailOut.model_validate(news, from_attributes=True)
