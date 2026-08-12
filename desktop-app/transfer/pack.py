"""Формат файла `.armwrestling` — переносимый архив соревнования.

Структура архива (ZIP, JSON внутри):

    metadata.json                — версия, id, счётчики, checksum
    competition.json             — запись tournaments + competition_source + session_id
    categories.json              — weight_categories
    participants.json            — participants
    matches.json                 — matches (все, включая незавершённые)
    athletes.json                — спортсмены, привязанные к соревнованию
    coaches.json                 — тренеры привязанных спортсменов
    clubs.json                   — клубы привязанных спортсменов/тренеров
    results.json                 — снапшот результатов (матчи со status='done')
    rating_events.json           — club_rating + club_rating_history соревнования
    overrides.json               — dvoeborie_overrides
    bracket_generations.json     — счётчики генераций сеток
    sync_operations.json         — pending-операции очереди синхронизации
    id_map.json                  — привязки локальный id -> серверный id
    photos/<имя>                 — фотографии (если включены в экспорт)

Чексумма: SHA-256 по содержимому всех файлов кроме metadata.json (он хранит
сам checksum). При импорте пересчитывается и сравнивается — любое изменение
файла даёт несовпадение.

Пароль (необязательно): «лёгкое» шифрование — ключ scrypt(пароль, соль),
XOR с потоком SHA-256. Это защита от случайного доступа к файлу, НЕ
криптографическая защита (смысл — обычные пользователи не откроют файл).
"""

import hashlib
import json
import os
import struct
import zipfile
import zlib
from datetime import datetime, timezone

# Версия формата экспорта. Ломать формат — только с инкрементом.
EXPORT_VERSION = 1
# Версия локальной схемы данных (armwrestling.db).
DATABASE_SCHEMA_VERSION = 1
# Версия приложения, вписываемая в metadata.
APP_VERSION = "1.6.0"

REQUIRED_MEMBERS = (
    "competition.json",
    "categories.json",
    "participants.json",
    "matches.json",
    "athletes.json",
    "coaches.json",
    "clubs.json",
    "results.json",
    "rating_events.json",
    "overrides.json",
    "bracket_generations.json",
    "sync_operations.json",
    "id_map.json",
)


class BackupFormatError(Exception):
    """Невалидный / повреждённый / несовместимый файл .armwrestling."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_json_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")


def json_rows(cursor_rows) -> list:
    """Преобразует список sqlite3.Row в список dict (сортировка ключей для
    стабильного checksum при повторном экспорте)."""
    out = []
    for row in cursor_rows:
        d = {k: row[k] for k in row.keys()}
        d = {k: (None if v is None else v) for k, v in d.items()}
        out.append(d)
    return out


# ─── checksum ─────────────────────────────────────────────────────
def compute_checksum(members: dict) -> str:
    """SHA-256 по отсортированному списку (имя, \\0, содержимое)."""
    h = hashlib.sha256()
    for name in sorted(members):
        h.update(name.encode("utf-8"))
        h.update(b"\x00")
        h.update(members[name])
    return h.hexdigest()


def checksum_members(payload: dict) -> dict:
    """Только обязательные разделы (фото — медиа, в checksum не входят)."""
    return {name: payload[name]
            for name in REQUIRED_MEMBERS if name in payload}


# ─── необязательное шифрование (scrypt + XOR-поток) ───────────────
def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32
    )


def _xor_stream(data: bytes, key: bytes) -> bytes:
    out = bytearray(len(data))
    for offset in range(0, len(data), 32):
        h = hashlib.sha256(key)
        h.update(struct.pack("<Q", offset // 32))
        stream = h.digest()
        chunk = data[offset:offset + 32]
        for i, b in enumerate(chunk):
            out[offset + i] = b ^ stream[i]
    return bytes(out)


def encrypt_payload(data: bytes, password: str, salt: bytes) -> bytes:
    return _xor_stream(data, derive_key(password, salt))


def decrypt_payload(data: bytes, password: str, salt: bytes) -> bytes:
    return _xor_stream(data, derive_key(password, salt))


# ─── запись / чтение архива ───────────────────────────────────────
def write_archive(dest_path: str, payload: dict, metadata: dict) -> None:
    """payload: имя -> bytes (все файлы, КРОМЕ metadata.json).
    metadata: dict; если нет checksum — считается по payload."""
    if "checksum" not in metadata:
        metadata = dict(metadata)
        metadata["checksum"] = compute_checksum(checksum_members(payload))
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(payload):
            zf.writestr(name, payload[name])
        zf.writestr("metadata.json", to_json_bytes(metadata))


def read_archive(src_path: str, password: str | None = None,
                 verify_checksum: bool = True) -> tuple:
    """Читает архив. Возвращает (payload, metadata) — payload уже
    декодирован в JSON-объекты. Бросает BackupFormatError."""
    if not os.path.exists(src_path):
        raise BackupFormatError("Файл не найден.")
    try:
        zf = zipfile.ZipFile(src_path)
    except (zipfile.BadZipFile, zlib.error, EOFError, ValueError):
        raise BackupFormatError("Файл повреждён — это не архив .armwrestling.")
    try:
        names = set(zf.namelist())
    except (zipfile.BadZipFile, zlib.error, EOFError, ValueError):
        raise BackupFormatError("Файл повреждён — не читается оглавление.")
    if "metadata.json" not in names:
        raise BackupFormatError(
            "В файле нет metadata.json — это не файл .armwrestling.")
    allowed = set(REQUIRED_MEMBERS) | {"metadata.json"}
    extra = sorted(n for n in names
                   if n not in allowed and not n.startswith("photos/"))
    if extra:
        raise BackupFormatError(
            "Файл повреждён или подделан: неожиданное содержимое "
            f"({', '.join(extra[:3])}).")
    try:
        metadata = json.loads(zf.read("metadata.json").decode("utf-8"))
    except (zipfile.BadZipFile, zlib.error, EOFError, ValueError):
        raise BackupFormatError("metadata.json повреждён (не читается).")
    except Exception:
        raise BackupFormatError("metadata.json повреждён.")
    for req in REQUIRED_MEMBERS:
        if req not in names:
            raise BackupFormatError(
                f"В файле отсутствует обязательный раздел {req}.")
    encrypted = bool(metadata.get("encrypted"))
    salt = b""
    if encrypted:
        if not password:
            raise BackupFormatError(
                "Файл защищён паролем — введите пароль.")
        try:
            salt = bytes.fromhex(metadata["salt"])
        except (KeyError, ValueError):
            raise BackupFormatError("metadata повреждён: нет соли шифрования.")
    raw: dict = {}
    payload = {}
    for name in REQUIRED_MEMBERS:
        try:
            data = zf.read(name)
        except (zipfile.BadZipFile, zlib.error, EOFError, ValueError):
            raise BackupFormatError(
                f"Раздел {name} повреждён (не читается).")
        if encrypted:
            try:
                data = decrypt_payload(data, password, salt)
            except Exception:
                raise BackupFormatError("Неверный пароль или файл повреждён.")
        raw[name] = data
        try:
            payload[name] = json.loads(data.decode("utf-8"))
        except Exception:
            raise BackupFormatError(f"Раздел {name} повреждён (не JSON).")
    if verify_checksum:
        expected = metadata.get("checksum")
        if not expected:
            raise BackupFormatError("В metadata отсутствует checksum.")
        if compute_checksum(raw) != expected:
            raise BackupFormatError(
                "Файл повреждён или был изменён (checksum не совпадает).")
    return payload, metadata


def read_member_bytes(src_path: str, name: str,
                      password: str | None = None, salt: bytes = b"") -> bytes:
    """Читает из архива один файл (например, фото) в байтах, расшифровывая
    при необходимости. Бросает BackupFormatError."""
    try:
        with zipfile.ZipFile(src_path) as zf:
            data = zf.read(name)
    except KeyError:
        raise BackupFormatError(f"В файле нет раздела {name}.")
    except (zipfile.BadZipFile, zlib.error, EOFError, ValueError):
        raise BackupFormatError("Файл повреждён — это не архив .armwrestling.")
    if password:
        try:
            data = decrypt_payload(data, password, salt)
        except Exception:
            raise BackupFormatError("Неверный пароль или файл повреждён.")
    return data


def check_version(metadata: dict) -> None:
    """Проверяет совместимость версий формата и схемы данных."""
    try:
        ev = int(metadata.get("export_version", 0))
    except (TypeError, ValueError):
        raise BackupFormatError("metadata повреждён: export_version.")
    if ev > EXPORT_VERSION:
        raise BackupFormatError(
            f"Файл создан более новой версией приложения "
            f"(export_version={ev}, поддерживается до {EXPORT_VERSION}).\n"
            "Обновите приложение на этом компьютере.")
    try:
        sv = int(metadata.get("database_schema_version", 0))
    except (TypeError, ValueError):
        raise BackupFormatError("metadata повреждён: database_schema_version.")
    if sv > DATABASE_SCHEMA_VERSION:
        raise BackupFormatError(
            f"Файл использует более новую схему данных "
            f"(schema={sv}, поддерживается до {DATABASE_SCHEMA_VERSION}).\n"
            "Обновите приложение на этом компьютере.")
