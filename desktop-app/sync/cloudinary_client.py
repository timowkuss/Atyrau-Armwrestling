"""Загрузка фото в Cloudinary напрямую с десктопа.

Раньше desktop-приложение копировало выбранный файл в локальную папку
photos/ и хранило photo_path как ЛОКАЛЬНЫЙ путь на диске конкретного
судейского компьютера. Этот путь потом улетал в sync_manager (create_athlete/
create_coach) как есть — сервер получал "photos/ivan.jpg", который не
существует нигде, кроме машины, где было выбрано фото. Из-за этого сайт и
десктоп физически не могли показывать одно и то же изображение.

Теперь фото загружается в Cloudinary СРАЗУ при выборе файла (см. choose_photo
в armwrestling_tournament.py), и в photo_path/БД/sync всегда попадает ГОТОВАЯ
Cloudinary-ссылка (secure_url) — то же самое, что хранит и отдаёт сайт.
Десктоп и сайт в итоге ссылаются на один и тот же файл в облаке.

Используется unsigned upload preset (Cloudinary Dashboard -> Settings ->
Upload -> Add upload preset, Signing Mode = Unsigned). Это осознанный выбор:
десктоп-приложение раздаётся судьям на разных компьютерах, и хранить на них
CLOUDINARY_API_SECRET (которым можно грузить/удалять что угодно в аккаунте)
небезопасно. Cloud name и имя пресета секретными не являются — их же видно
в любом запросе к Cloudinary из браузера на сайте.

Настройка (один раз):
    1. В Cloudinary Dashboard создать unsigned upload preset, например
       "armwrestling_desktop".
    2. Задать переменные окружения на компьютере судьи (или в .env рядом
       с armwrestling_tournament.py, если в проекте уже используется
       python-dotenv):
           CLOUDINARY_CLOUD_NAME=<твой cloud name>
           CLOUDINARY_UPLOAD_PRESET=armwrestling_desktop
"""

import os
from pathlib import Path

import requests

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_UPLOAD_PRESET = os.environ.get("CLOUDINARY_UPLOAD_PRESET", "")

_UPLOAD_URL_TMPL = "https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
_TIMEOUT_SECONDS = 30


class CloudinaryUploadError(Exception):
    """Не удалось загрузить фото в Cloudinary (нет сети, нет настроек,
    сервис Cloudinary вернул ошибку и т.п.). Ловится в UI — при неудаче
    приложение НЕ должно падать, а должно предупредить организатора."""


def is_configured() -> bool:
    return bool(CLOUDINARY_CLOUD_NAME and CLOUDINARY_UPLOAD_PRESET)


def upload_photo(local_file_path: str, folder: str) -> str:
    """Загружает файл в Cloudinary и возвращает secure_url.

    local_file_path: путь к файлу, который только что выбрали в filedialog.
    folder: "athletes" / "coaches" — просто для порядка в медиатеке
            Cloudinary, на саму синхронизацию не влияет.
    """
    if not is_configured():
        raise CloudinaryUploadError(
            "Cloudinary не настроен: задайте переменные окружения "
            "CLOUDINARY_CLOUD_NAME и CLOUDINARY_UPLOAD_PRESET "
            "(см. комментарий в sync/cloudinary_client.py)."
        )
    p = Path(local_file_path)
    if not p.exists():
        raise CloudinaryUploadError(f"Файл не найден: {local_file_path}")

    url = _UPLOAD_URL_TMPL.format(cloud_name=CLOUDINARY_CLOUD_NAME)
    try:
        with open(p, "rb") as f:
            resp = requests.post(
                url,
                files={"file": (p.name, f)},
                data={"upload_preset": CLOUDINARY_UPLOAD_PRESET, "folder": folder},
                timeout=_TIMEOUT_SECONDS,
            )
    except requests.RequestException as e:
        raise CloudinaryUploadError(f"Нет соединения с Cloudinary: {e}") from e

    if resp.status_code != 200:
        raise CloudinaryUploadError(
            f"Cloudinary вернул ошибку {resp.status_code}: {resp.text[:300]}"
        )

    body = resp.json()
    secure_url = body.get("secure_url")
    if not secure_url:
        raise CloudinaryUploadError(f"В ответе Cloudinary нет secure_url: {body}")
    return secure_url
