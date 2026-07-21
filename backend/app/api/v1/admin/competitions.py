from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.competitions import Competition
from app.db.models.geo import City
from app.db.models.media import Document
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.competitions import CategoryOut, CompetitionAdminUpdate, CompetitionDetailOut
from app.schemas.media import DocumentCreate, DocumentOut

router = APIRouter(prefix="/competitions", tags=["admin:competitions"])

WRITE_ROLES = ("super_admin", "admin")


@router.get("", response_model=list[CompetitionDetailOut])
def list_competitions_admin(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """И draft, и published — в отличие от /public/competitions, который
    по умолчанию отдаёт только published. Организатор мог уже завести
    турнир в десктопе (ARCHITECTURE.md §5), админ сайта готовит
    инфо-часть заранее, до публикации."""
    competitions = db.query(Competition).order_by(Competition.date.desc()).all()
    out = []
    for c in competitions:
        city_name = db.get(City, c.location_city_id).name if c.location_city_id else None
        out.append(
            CompetitionDetailOut(
                id=c.id,
                name=c.name,
                date=c.date,
                location_city_name=city_name,
                organizer=c.organizer,
                description=c.description,
                poster_path=c.poster_path,
                regulations_doc_path=c.regulations_doc_path,
                status=c.status,
                participants_count=len(c.participants),
                weight_tolerance=c.weight_tolerance,
                bracket_system=c.bracket_system,
                format_type=c.format_type,
                categories=[CategoryOut(id=cat.id, name=cat.name, hand=cat.hand) for cat in c.categories],
            )
        )
    return out


@router.get("/{competition_id}/documents", response_model=list[DocumentOut])
def list_documents(
    competition_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    docs = (
        db.query(Document)
        .filter(Document.competition_id == competition_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return [DocumentOut.model_validate(d, from_attributes=True) for d in docs]


@router.patch("/{competition_id}")
def update_competition(
    competition_id: int,
    payload: CompetitionAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Редактирует ТОЛЬКО информационную часть турнира. Схема
    CompetitionAdminUpdate физически не содержит полей сетки, результатов,
    участников или очков — их нельзя передать сюда даже по ошибке фронта.
    Всё это — исключительно через Desktop (см. ARCHITECTURE.md §6)."""
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(competition, field, value)
    db.commit()
    return {"status": "ok"}


@router.post("/{competition_id}/documents", status_code=201)
def add_document(
    competition_id: int,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    if payload.competition_id != competition_id:
        raise HTTPException(status_code=400, detail="competition_id в теле и в пути не совпадают")

    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    document = Document(**payload.model_dump())
    db.add(document)
    db.commit()
    db.refresh(document)
    return {"id": document.id}


@router.delete("/{competition_id}/documents/{document_id}")
def delete_document(
    competition_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.competition_id == competition_id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    db.delete(document)
    db.commit()
    return {"status": "deleted"}
