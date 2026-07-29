import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Простой in-memory rate limiter для /login.
# Ключ — IP клиента, значение — список timestamp-ов попыток.
_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_RATE_LIMIT = 10  # не более 10 попыток за окно
_LOGIN_RATE_WINDOW = 60  # окно в секундах


def _check_login_rate(request: Request):
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    attempts = _login_attempts[ip]
    # Отбрасываем попытки старше окна
    cutoff = now - _LOGIN_RATE_WINDOW
    _login_attempts[ip] = [t for t in attempts if t > cutoff]
    if len(_login_attempts[ip]) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте через минуту.",
        )
    _login_attempts[ip].append(now)


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db), request: Request = None):
    _check_login_rate(request)
    user = db.query(User).filter(User.username == payload.username).first()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
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
