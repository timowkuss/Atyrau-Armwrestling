from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models.geo import City, Region
from app.db.session import get_db
from app.schemas.geo import CityOut

router = APIRouter(prefix="/reference", tags=["public:reference"])


@router.get("/cities", response_model=list[CityOut])
def list_cities(db: Session = Depends(get_db)):
    """Справочник городов для форм админки (клубы/тренеры/спортсмены/
    турниры) — отдельного экрана управления городами в Этапе 5 нет."""
    rows = (
        db.query(City, Region.name.label("region_name"))
        .join(Region, City.region_id == Region.id)
        .order_by(City.name)
        .all()
    )
    return [CityOut(id=city.id, name=city.name, region_name=region_name) for city, region_name in rows]
