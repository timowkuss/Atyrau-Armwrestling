"""Создаёт пользователя сайта (обычно первого super_admin, с которого
дальше можно управлять остальными через /api/v1/admin/*).

Запуск:
    venv/bin/python -m app.db.create_user \\
        --username admin --email admin@atyrauarmsport.kz \\
        --password "change-me" --full-name "Главный администратор" \\
        --role super_admin
"""

import argparse

from app.core.security import hash_password
from app.db.models.users import Role, User
from app.db.session import SessionLocal


def create_user(username: str, email: str, password: str, full_name: str, role_code: str):
    db = SessionLocal()
    try:
        role = db.query(Role).filter_by(code=role_code).first()
        if role is None:
            raise SystemExit(
                f"Роль '{role_code}' не найдена. Сначала прогоните "
                f"`python -m app.db.seed`."
            )
        if db.query(User).filter_by(username=username).first():
            raise SystemExit(f"Пользователь '{username}' уже существует.")

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role_id=role.id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Пользователь '{username}' ({role_code}) создан.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument(
        "--role",
        required=True,
        choices=["super_admin", "admin", "editor", "guest"],
    )
    args = parser.parse_args()
    create_user(args.username, args.email, args.password, args.full_name, args.role)
