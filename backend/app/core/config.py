from pydantic_settings import BaseSettings, SettingsConfigDict

# Значения-заглушки из .env.example: если их оставить без замены — любой,
# кто прочитал репозиторий, подделает JWT суперадмина и получит полный
# доступ к /sync/*. Такие значения должны отклоняться при старте.
_FORBIDDEN_PLACEHOLDERS = {
    "change-me",
    "change-me-in-production",
    "change-me-desktop-sync-token",
    "changeme",
    "secret",
    "secret-key",
    "your-secret",
    "your-secret-key",
    "password",
    "12345678",
}

# Минимальная длина JWT_SECRET: 32 символа — короткие ключи поддаются
# брутфорсу подписи HS256.
JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    """Настройки приложения. Значения переопределяются переменными окружения
    или файлом .env (см. .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://armsport:armsport@localhost:5432/armsport"

    # "production" — в проде отключается Swagger UI (/docs), "development" — для
    # локальной разработки.
    ENVIRONMENT: str = "development"

    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    DESKTOP_SYNC_TOKEN: str = ""

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    def model_post_init(self, __context):
        problems = []
        if not self.JWT_SECRET:
            problems.append("JWT_SECRET не задан")
        elif self.JWT_SECRET.lower() in _FORBIDDEN_PLACEHOLDERS:
            problems.append("JWT_SECRET использует публичное значение-заглушку из .env.example")
        elif len(self.JWT_SECRET) < JWT_SECRET_MIN_LENGTH:
            problems.append(
                f"JWT_SECRET слишком короткий (минимум {JWT_SECRET_MIN_LENGTH} символов)"
            )
        if not self.DESKTOP_SYNC_TOKEN:
            problems.append("DESKTOP_SYNC_TOKEN не задан")
        elif self.DESKTOP_SYNC_TOKEN.lower() in _FORBIDDEN_PLACEHOLDERS:
            problems.append(
                "DESKTOP_SYNC_TOKEN использует публичное значение-заглушку из .env.example"
            )
        if problems:
            raise RuntimeError(
                "Некорректная конфигурация: " + "; ".join(problems)
                + ". Задайте сильные случайные значения в .env или переменных окружения."
            )


settings = Settings()
