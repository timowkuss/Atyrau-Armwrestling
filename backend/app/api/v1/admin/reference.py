from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.models.geo import City, Country, Region
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.geo import CityOut

router = APIRouter(prefix="/reference", tags=["admin:reference"])

WRITE_ROLES = ("super_admin", "admin", "editor")

# Регион по умолчанию для городов/районов, которые вводят свободным текстом
# в формах админки (тренеры/клубы/спортсмены/турниры). Федерация базируется
# в Атырауской области, поэтому новые записи по умолчанию относим сюда —
# при необходимости их всегда можно перенести в другой регион через БД.
DEFAULT_COUNTRY = "Казахстан"
DEFAULT_REGION = "Атырауская область"


class CityResolveIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название города не может быть пустым")
        return value


@router.post("/cities", response_model=CityOut)
def resolve_city(
    payload: CityResolveIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Находит город по имени (без учёта регистра) или создаёт новый —
    используется полями свободного ввода города в формах админки, вместо
    выбора строго из предзаполненного справочника."""
    existing = (
        db.query(City)
        .filter(City.name.ilike(payload.name))
        .join(Region, City.region_id == Region.id)
        .add_columns(Region.name.label("region_name"))
        .first()
    )
    if existing:
        city, region_name = existing
        return CityOut(id=city.id, name=city.name, region_name=region_name)

    country = db.query(Country).filter_by(name=DEFAULT_COUNTRY).first()
    if not country:
        country = Country(name=DEFAULT_COUNTRY, code="KZ")
        db.add(country)
        db.flush()

    region = db.query(Region).filter_by(name=DEFAULT_REGION, country_id=country.id).first()
    if not region:
        region = Region(name=DEFAULT_REGION, country_id=country.id)
        db.add(region)
        db.flush()

    city = City(name=payload.name, region_id=region.id)
    db.add(city)
    db.commit()
    db.refresh(city)
    return CityOut(id=city.id, name=city.name, region_name=region.name)
