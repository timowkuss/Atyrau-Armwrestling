from datetime import datetime

from pydantic import BaseModel


class GalleryAlbumOut(BaseModel):
    id: int
    competition_id: int | None
    title: str | None
    created_at: datetime


class GalleryAlbumCreate(BaseModel):
    competition_id: int | None = None
    title: str | None = None


class PhotoOut(BaseModel):
    id: int
    album_id: int | None
    competition_id: int | None
    athlete_id: int | None
    url: str
    caption: str | None


class PhotoCreate(BaseModel):
    album_id: int | None = None
    competition_id: int | None = None
    athlete_id: int | None = None
    url: str
    caption: str | None = None


class VideoOut(BaseModel):
    id: int
    competition_id: int | None
    news_id: int | None
    title: str | None
    url: str


class VideoCreate(BaseModel):
    competition_id: int | None = None
    news_id: int | None = None
    title: str | None = None
    url: str


class DocumentOut(BaseModel):
    id: int
    competition_id: int
    title: str
    file_path: str
    doc_type: str | None


class DocumentCreate(BaseModel):
    competition_id: int
    title: str
    file_path: str
    doc_type: str | None = None
