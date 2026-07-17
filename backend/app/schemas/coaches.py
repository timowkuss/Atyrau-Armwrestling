from pydantic import BaseModel


class CoachListOut(BaseModel):
    id: int
    full_name: str
    photo_path: str | None
    club_name: str | None
    athletes_count: int


class CoachDetailOut(BaseModel):
    id: int
    full_name: str
    photo_path: str | None
    bio: str | None
    club_name: str | None
    athletes_count: int


class CoachCreate(BaseModel):
    full_name: str
    photo_path: str | None = None
    bio: str | None = None
    club_id: int | None = None


class CoachUpdate(BaseModel):
    full_name: str | None = None
    photo_path: str | None = None
    bio: str | None = None
    club_id: int | None = None
