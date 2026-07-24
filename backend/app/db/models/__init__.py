"""Импортирует все ORM-модели, чтобы Base.metadata содержала все таблицы —
это нужно Alembic для автогенерации миграций (env.py импортирует этот пакет)."""

from app.db.models.geo import Country, Region, City  # noqa: F401
from app.db.models.users import Role, User  # noqa: F401
from app.db.models.clubs import Club  # noqa: F401
from app.db.models.coaches import Coach  # noqa: F401
from app.db.models.athletes import Athlete  # noqa: F401
from app.db.models.categories import AgeCategory, WeightCategory, Category  # noqa: F401
from app.db.models.competitions import Competition, CompetitionParticipant  # noqa: F401
from app.db.models.matches import Match  # noqa: F401
from app.db.models.results import Result  # noqa: F401
from app.db.models.statistics import AthleteStatistic  # noqa: F401
from app.db.models.rankings import AthleteRanking, ClubRanking  # noqa: F401
from app.db.models.news import News  # noqa: F401
from app.db.models.media import GalleryAlbum, Photo, Video, Document  # noqa: F401
from app.db.models.sync_tombstone import SyncTombstone  # noqa: F401
