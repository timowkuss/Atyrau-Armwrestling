from datetime import datetime

from pydantic import BaseModel


class NewsListOut(BaseModel):
    id: int
    title: str
    slug: str
    cover_photo_path: str | None
    is_published: bool
    published_at: datetime | None


class NewsDetailOut(NewsListOut):
    content: str | None


class NewsCreate(BaseModel):
    title: str
    slug: str
    content: str | None = None
    cover_photo_path: str | None = None
    is_published: bool = False


class NewsUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    content: str | None = None
    cover_photo_path: str | None = None
    is_published: bool | None = None
