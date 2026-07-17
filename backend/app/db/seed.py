"""Наполняет справочники минимальными данными, необходимыми для старта:
роли, страна/регионы/города, базовые весовые и возрастные категории.

Запуск:
    cd backend && venv/bin/python -m app.db.seed
"""

from app.db.models.geo import City, Country, Region
from app.db.models.users import Role
from app.db.models.categories import AgeCategory, WeightCategory
from app.db.session import SessionLocal


ROLES = [
    ("super_admin", "Супер-администратор"),
    ("admin", "Администратор"),
    ("editor", "Редактор"),
    ("guest", "Гость"),
]

# страна -> [(регион, [города])]
GEO = {
    "Казахстан": {
        "Атырауская область": ["Атырау", "Кульсары"],
        "город Алматы": ["Алматы"],
        "город Астана": ["Астана"],
        "Мангистауская область": ["Актау"],
    }
}

AGE_CATEGORIES = [
    ("Дети", 10, 12),
    ("Юноши/девушки 13-15", 13, 15),
    ("Юниоры 16-18", 16, 18),
    ("Взрослые", 19, 39),
    ("Ветераны", 40, None),
]

WEIGHT_CATEGORIES = [
    # (название, макс. вес, пол)
    ("до 60 кг", 60, "male"),
    ("до 70 кг", 70, "male"),
    ("до 80 кг", 80, "male"),
    ("до 90 кг", 90, "male"),
    ("до 100 кг", 100, "male"),
    ("свыше 100 кг", None, "male"),
    ("до 55 кг", 55, "female"),
    ("до 65 кг", 65, "female"),
    ("до 75 кг", 75, "female"),
    ("свыше 75 кг", None, "female"),
]


def seed():
    db = SessionLocal()
    try:
        # --- роли ---
        for code, name in ROLES:
            if not db.query(Role).filter_by(code=code).first():
                db.add(Role(code=code, name=name))
        db.flush()

        # --- география ---
        for country_name, regions in GEO.items():
            country = db.query(Country).filter_by(name=country_name).first()
            if not country:
                country = Country(name=country_name, code="KZ")
                db.add(country)
                db.flush()
            for region_name, cities in regions.items():
                region = (
                    db.query(Region)
                    .filter_by(name=region_name, country_id=country.id)
                    .first()
                )
                if not region:
                    region = Region(name=region_name, country_id=country.id)
                    db.add(region)
                    db.flush()
                for city_name in cities:
                    exists = (
                        db.query(City)
                        .filter_by(name=city_name, region_id=region.id)
                        .first()
                    )
                    if not exists:
                        db.add(City(name=city_name, region_id=region.id))

        # --- возрастные категории ---
        for name, min_age, max_age in AGE_CATEGORIES:
            if not db.query(AgeCategory).filter_by(name=name).first():
                db.add(AgeCategory(name=name, min_age=min_age, max_age=max_age))

        # --- весовые категории ---
        for name, max_weight, gender in WEIGHT_CATEGORIES:
            exists = (
                db.query(WeightCategory)
                .filter_by(name=name, gender=gender)
                .first()
            )
            if not exists:
                db.add(
                    WeightCategory(name=name, max_weight=max_weight, gender=gender)
                )

        db.commit()
        print("Сиды успешно загружены.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
