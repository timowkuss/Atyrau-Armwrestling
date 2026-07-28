from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Значения переопределяются переменными окружения
    или файлом .env (см. .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://armsport:armsport@localhost:5432/armsport"

    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # Отдельный токен для десктоп-приложения (scope "desktop_sync"),
    # не совпадает с пользовательскими JWT сайта.
    DESKTOP_SYNC_TOKEN: str = "change-me-desktop-sync-token"

    # ─── Загрузка фото (тренеры/спортсмены) через Cloudinary ───
    # Бесплатный аккаунт на cloudinary.com даёт эти три значения.
    # Если не заданы — эндпоинт /admin/media/upload вернёт понятную ошибку
    # вместо непонятного 500, чтобы сразу было видно, что не настроено.
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""


settings = Settings()
