"""Перенос соревнования между компьютерами: экспорт/импорт .armwrestling,
авто-бэкапы, аварийный экспорт. См. COMPETITION_TRANSFER.md."""

from .pack import (EXPORT_VERSION, DATABASE_SCHEMA_VERSION, APP_VERSION,
                   BackupFormatError)
from .exporter import export_competition, ExportError, validate_competition_integrity
from .importer import (import_competition, preview_archive,
                       CompetitionExistsError, IdCollisionError,
                       ImportValidationError)
from .backup_manager import BackupManager

__all__ = [
    "EXPORT_VERSION", "DATABASE_SCHEMA_VERSION", "APP_VERSION",
    "BackupFormatError", "export_competition", "ExportError",
    "validate_competition_integrity", "import_competition", "preview_archive",
    "CompetitionExistsError", "IdCollisionError", "ImportValidationError",
    "BackupManager",
]
