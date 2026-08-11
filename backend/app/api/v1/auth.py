import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Простой in-memory rate limiter для /login.
# Ключ — IP клиента, значение — список timestamp-ов попыток.
_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_RATE_LIMIT = 10  # не более 10 попыток за окно
_LOGIN_RATE_WINDOW = 60  # окно в секундах

# Дополнительный лимит на один логин (username): распределённый брутфорс
# одного пароля с разных IP не обходит его.
_username_attempts: dict[str, list[float]] = defaultdict(list)
_USERNAME_RATE_LIMIT = 10
_USERNAME_RATE_WINDOW = 60

# Фиктивный bcrypt-хэш для несуществующих пользователей: verify_password
# выполняется всегда (даже когда пользователя нет), чтобы время ответа
# не зависело от существования аккаунта (timing side-channel для
# перебора имён пользователей).
_DUMMY_HASH = hash_password("dummy-password-for-timing")

# Число bcrypt-итераций у real-хэша vs dummy-хэша различаться не будут
# (оба созданы gensalt()) — сравнение по времени не раскрывает разницу.


def _client_ip(request: Request) -> str:
    """Реальный IP клиента: за reverse-proxy (Railway/Vercel) request.client
    это IP прокси, у всех клиентов он одинаковый — и лимит становится
    глобальным (10 попыток на всех). Берём последний hop из
    X-Forwarded-For, который добавляет прокси."""
    if request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_login_rate(request: Request, username: str):
    now = time.time()
    ip = _client_ip(request)
    cutoff = now - _LOGIN_RATE_WINDOW
    _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
    _username_attempts[username] = [
        t for t in _username_attempts[username] if t > cutoff
    ]
    if (
        len(_login_attempts[ip]) >= _LOGIN_RATE_LIMIT
        or len(_username_attempts[username]) >= _USERNAME_RATE_LIMIT
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте через минуту.",
        )
    _login_attempts[ip].append(now)
    _username_attempts[username].append(now)


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db), request: Request = None):
    _check_login_rate(request, payload.username)
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not user.is_active:
        # Пользователя нет/деактивирован — всё равно выполняем bcrypt-сверку
        # против фиктивного хэша, чтобы время ответа не раскрывало
        # существование аккаунта.
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    token = create_access_token(subject=user.username, role=user.role.code)
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        role_code=current_user.role.code,
    )
