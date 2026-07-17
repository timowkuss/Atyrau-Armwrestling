from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.media import GalleryAlbum, Photo, Video
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.media import (
    GalleryAlbumCreate,
    GalleryAlbumOut,
    PhotoCreate,
    PhotoOut,
    VideoCreate,
    VideoOut,
)

router = APIRouter(prefix="/gallery", tags=["admin:gallery"])

WRITE_ROLES = ("super_admin", "admin", "editor")


@router.get("/albums", response_model=list[GalleryAlbumOut])
def list_albums(db: Session = Depends(get_db), _: User = Depends(require_role(*WRITE_ROLES))):
    albums = db.query(GalleryAlbum).order_by(GalleryAlbum.created_at.desc()).all()
    return [GalleryAlbumOut.model_validate(a, from_attributes=True) for a in albums]


@router.get("/photos", response_model=list[PhotoOut])
def list_photos(
    album_id: int | None = None,
    competition_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    query = db.query(Photo)
    if album_id is not None:
        query = query.filter(Photo.album_id == album_id)
    if competition_id is not None:
        query = query.filter(Photo.competition_id == competition_id)
    photos = query.order_by(Photo.uploaded_at.desc()).all()
    return [PhotoOut.model_validate(p, from_attributes=True) for p in photos]


@router.get("/videos", response_model=list[VideoOut])
def list_videos(db: Session = Depends(get_db), _: User = Depends(require_role(*WRITE_ROLES))):
    videos = db.query(Video).order_by(Video.uploaded_at.desc()).all()
    return [VideoOut.model_validate(v, from_attributes=True) for v in videos]


@router.post("/albums", status_code=201)
def create_album(
    payload: GalleryAlbumCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    album = GalleryAlbum(**payload.model_dump())
    db.add(album)
    db.commit()
    db.refresh(album)
    return {"id": album.id}


@router.post("/photos", status_code=201)
def create_photo(
    payload: PhotoCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    photo = Photo(**payload.model_dump())
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return {"id": photo.id}


@router.delete("/photos/{photo_id}")
def delete_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if photo is None:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    db.delete(photo)
    db.commit()
    return {"status": "deleted"}


@router.post("/videos", status_code=201)
def create_video(
    payload: VideoCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    video = Video(**payload.model_dump())
    db.add(video)
    db.commit()
    db.refresh(video)
    return {"id": video.id}


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    db.delete(video)
    db.commit()
    return {"status": "deleted"}
