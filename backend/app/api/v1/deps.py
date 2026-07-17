from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.models.users import User
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Проверяет JWT пользователя сайта и возвращает объект User с ролью."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.username == payload["sub"]).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или деактивирован",
        )
    return user


def require_role(*allowed_role_codes: str):
    """Фабрика зависимостей: пускает только пользователей с одной из
    перечисленных ролей (коды ролей — super_admin/admin/editor/guest,
    см. ARCHITECTURE.md §6)."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.code not in allowed_role_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Роль '{current_user.role.code}' не имеет доступа "
                    f"к этому действию"
                ),
            )
        return current_user

    return checker


def require_desktop_sync(x_sync_token: str | None = Header(default=None)):
    """Отдельная авторизация для десктоп-приложения — статический
    service-token в заголовке X-Sync-Token, НЕ пользовательский JWT
    (см. ARCHITECTURE.md §4.3: desktop_sync шире прав любого сайтового
    админа, но выдаётся только доверенному клиенту-организатору)."""
    if not x_sync_token or x_sync_token != settings.DESKTOP_SYNC_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или отсутствующий X-Sync-Token",
        )
    return True
