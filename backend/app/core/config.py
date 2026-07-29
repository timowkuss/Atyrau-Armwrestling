from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Значения переопределяются переменными окружения
    или файлом .env (см. .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://armsport:armsport@localhost:5432/armsport"

    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    DESKTOP_SYNC_TOKEN: str = ""

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    def model_post_init(self, __context):
        missing = []
        if not self.JWT_SECRET:
            missing.append("JWT_SECRET")
        if not self.DESKTOP_SYNC_TOKEN:
            missing.append("DESKTOP_SYNC_TOKEN")
        if missing:
            raise RuntimeError(
                "Не заданы обязательные переменные окружения: "
                + ", ".join(missing)
                + ". Добавьте их в .env или переменные окружения."
            )


settings = Settings()
