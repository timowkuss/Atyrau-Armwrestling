# Atyrau Armsport — Backend, Этап 1

Этот пакет закрывает Этап 1 из ARCHITECTURE.md: модели SQLAlchemy под всю
схему БД, Alembic-миграции и сиды справочников. API-роуты (Этап 2-3) сюда
ещё не входят.

Проверено вживую: миграция накатана на настоящий локальный PostgreSQL 16,
все 22 таблицы + FK/CHECK-constraints созданы корректно, downgrade/upgrade
обратимы, сиды идемпотентны (повторный запуск не плодит дубли).

## Установка

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # и поправить DATABASE_URL под свою БД
```

## PostgreSQL

Нужна база и пользователь (пример):

```sql
CREATE USER armsport WITH PASSWORD 'armsport';
CREATE DATABASE armsport OWNER armsport;
```

## Миграции

```bash
alembic upgrade head             # создать все таблицы
alembic downgrade base           # откатить всё (для проверки/пересборки)
alembic revision --autogenerate -m "описание изменения"   # новая миграция при изменении моделей
```

## Сиды справочников

```bash
python -m app.db.seed
```

Заполняет: роли (`super_admin`, `admin`, `editor`, `guest`), базовую
географию (Казахстан → несколько областей и городов, легко расширить в
`app/db/seed.py`), возрастные и весовые категории. Скрипт идемпотентный —
безопасно запускать повторно.

## Структура

```
backend/
├── app/
│   ├── core/config.py       # настройки (DATABASE_URL, JWT, DESKTOP_SYNC_TOKEN)
│   └── db/
│       ├── base.py          # Base для всех моделей
│       ├── session.py       # engine/SessionLocal/get_db
│       ├── seed.py          # сиды справочников
│       └── models/          # по одному файлу на домен (см. ARCHITECTURE.md §3)
├── alembic/
│   ├── env.py                # подключён к settings.DATABASE_URL и Base.metadata
│   └── versions/
│       └── ..._initial_schema.py
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Дальше — Этап 2

FastAPI-скелет + auth (users/roles, JWT login), см. дорожную карту в
ARCHITECTURE.md §7.

---

## Этап 2 — FastAPI-скелет + авторизация (готово)

Добавлено:

- `app/main.py` — точка входа FastAPI, CORS для будущего фронтенда.
- `app/core/security.py` — хэширование паролей (bcrypt напрямую — passlib
  конфликтует с новыми версиями bcrypt, поэтому не используется), JWT
  (create/decode).
- `app/api/v1/deps.py` — три зависимости:
  - `get_current_user` — проверяет JWT пользователя сайта;
  - `require_role(*codes)` — фабрика для ограничения по ролям
    (super_admin/admin/editor/guest);
  - `require_desktop_sync` — отдельная, простая проверка статического
    `X-Sync-Token` для десктоп-приложения (НЕ пользовательский JWT — см.
    ARCHITECTURE.md §4.3).
- `app/api/v1/auth.py` — `POST /api/v1/auth/login`, `GET /api/v1/auth/me`.
- Заглушки с реальной проверкой доступа (полноценные маршруты — Этапы 3/5/6-7):
  - `GET /api/v1/public/ping` — без авторизации;
  - `GET /api/v1/admin/ping` — только super_admin/admin/editor;
  - `GET /api/v1/sync/ping` — только с `X-Sync-Token`.
- `app/db/create_user.py` — создание пользователя (первым делом — super_admin).

### Запуск

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

Swagger: http://localhost:8000/docs

Создать первого администратора (после `alembic upgrade head` и `python -m app.db.seed`):

```bash
python -m app.db.create_user --username admin --email admin@atyrauarmsport.kz \
  --password "смените-меня" --full-name "Главный администратор" --role super_admin
```

### Проверено вживую (curl)

| Запрос | Результат |
|---|---|
| `GET /api/v1/admin/ping` без токена | `401 Требуется авторизация` |
| `POST /api/v1/auth/login` неверный пароль | `401 Неверный логин или пароль` |
| `POST /api/v1/auth/login` верный пароль | `200`, JWT с `role` в payload |
| `GET /api/v1/admin/ping` с токеном super_admin | `200 {"role": "super_admin"}` |
| `GET /api/v1/admin/ping` с токеном guest | `403` (роль не в списке разрешённых) |
| `GET /api/v1/sync/ping` без `X-Sync-Token` | `401` |
| `GET /api/v1/sync/ping` с верным `X-Sync-Token` | `200` |
| `GET /api/v1/public/ping` | `200` (без авторизации) |

## Дальше — Этап 3

Public read API: `athletes/clubs/coaches/competitions` + тестовые данные
(см. ARCHITECTURE.md §7).

---

## Этап 3 — Public read API + демо-данные (готово)

Добавлено:

- `app/schemas/{athletes,clubs,coaches,competitions,common}.py` — Pydantic-схемы
  ответов, включая `Page[T]` для пагинации.
- `app/api/v1/public/athletes.py`:
  - `GET /athletes` — фильтры `name, club_id, city_id, coach_id, age,
    weight_category_id, rank, gender` + пагинация;
  - `GET /athletes/{id}` — карточка со статистикой (учитывает
    `is_manual_override`, просто отдаёт то, что лежит в `athlete_statistics`);
  - `GET /athletes/{id}/history` — история турниров/мест/медалей;
  - `GET /athletes/{id}/matches` — история матчей с соперником и исходом.
- `app/api/v1/public/clubs.py` — список (фильтр `city_id`) + карточка.
- `app/api/v1/public/coaches.py` — список (фильтр `club_id`) + карточка.
- `app/api/v1/public/competitions.py`:
  - `GET /competitions` — фильтры `year, status` (по умолчанию `published`);
  - `GET /competitions/{id}` — карточка с категориями;
  - `GET /competitions/{id}/results` — итоговые места/медали;
  - `GET /competitions/{id}/bracket` — сетка **только на просмотр**.
- `app/db/seed_demo_data.py` — идемпотентные демо-данные: 2 клуба, 2 тренера,
  8 спортсменов, 1 опубликованный турнир с 2 категориями, полуфиналами и
  финалами, итоговыми результатами и статистикой.

### Проверено вживую (curl, реальный Postgres)

| Проверка | Результат |
|---|---|
| `GET /athletes?name=Ерлан` | находит 1 из 8, точное совпадение по имени |
| `GET /athletes?gender=female` | 2 из 8 |
| `GET /athletes?weight_category_id=3` | ровно 4 участника мужской категории до 80 кг демо-турнира |
| `GET /athletes?age=27` | корректно вычисляется через `date_part('year', age(...))` |
| `GET /athletes/1` | карточка + статистика (2 победы, 1 золото) |
| `GET /athletes/1/history` | 1 турнир, место 1, золото |
| `GET /athletes/1/matches` | 2 матча (полуфинал + финал), оба выигранные |
| `GET /athletes/999` | `404 Спортсмен не найден` |
| `GET /clubs?city_id=<Алматы>` | только клуб Алматы |
| `GET /clubs/1` | клуб + число спортсменов/тренеров |
| `GET /competitions` | 1 турнир со статусом `published` |
| `GET /competitions/1/results` | все 6 мест по 2 категориям, с медалями |
| `GET /competitions/1/bracket` | 4 матча (2 полуфинала + 2 финала), с именами и статусом |

Один реальный баг поймал и исправил в процессе: в `Athlete` не было
relationship `city` (только `club`/`coach`) — обращение
`athlete.city.name` падало с `AttributeError`; заменено на прямой
`db.get(City, ...)`.

## Дальше — Этап 4

React-скелет: Home, Athletes, AthleteProfile, Competitions на публичном
API (см. ARCHITECTURE.md §7).

---

## Этап 5 — Админ-панель сайта: реальный CRUD (готово)

Добавлено (все — с проверкой ролей через `require_role`):

- **Спортсмены** (`super_admin`/`admin`): `POST/PATCH /admin/athletes`,
  `DELETE` — только `super_admin`. Отдельно —
  `PATCH /admin/athletes/{id}/statistics` (любое подмножество полей
  `athlete_statistics`; при сохранении автоматически ставится
  `is_manual_override=true`, пишется `overridden_by`/`overridden_at`) и
  `POST /admin/athletes/{id}/statistics/recalculate` (снимает флаг).
- **Клубы / Тренеры** (`super_admin`/`admin`): полный CRUD,
  `DELETE` — только `super_admin`.
- **Новости** (`super_admin`/`admin`/`editor`): CRUD, `published_at`
  проставляется автоматически при первой публикации.
- **Галерея** (`super_admin`/`admin`/`editor`): альбомы, фото, видео
  (URL/путь как строка — реальная загрузка файлов на диск/S3 будет
  добавлена отдельно, вне рамок Этапа 5).
- **Соревнования** (`super_admin`/`admin`): `PATCH /admin/competitions/{id}`
  — схема `CompetitionAdminUpdate` содержит **только**
  `description/poster_path/regulations_doc_path/location_city_id`. Плюс
  `POST/DELETE /admin/competitions/{id}/documents`.

### Проверено вживую (curl, реальные роли)

| Проверка | Результат |
|---|---|
| Создать клуб как `admin` | `201` |
| Создать клуб как `editor` | `403` (не в списке ролей для клубов) |
| Создать новость как `editor` | `201`, `published_at` выставлен автоматически |
| `PATCH /admin/competitions/1` с подсунутыми `winner_id`, `status`, `participants` | поля молча отброшены Pydantic-схемой, в БД реально поменялось только `description`, `status` остался `published` |
| `PATCH /admin/athletes/1/statistics` (`total_wins: 1`) | `is_manual_override=true`, `overridden_by`/`overridden_at` заполнены |
| Гость правит статистику | `403` |
| `DELETE /admin/athletes/{id}` ролью `admin` (не super_admin) | `403` |
| `DELETE /admin/athletes/{id}` ролью `super_admin` | проходит проверку роли (в тесте — `404`, т.к. id не существовал) |
| `PATCH /admin/clubs/{id}` ролью `admin` | `200` |

Ключевая проверка архитектурного решения §6: сетку/результаты/участников
через сайт **невозможно** изменить не потому что где-то стоит `if`, а
потому что в `CompetitionAdminUpdate` этих полей просто нет — даже прямой
curl с этими полями в теле их тихо игнорирует.

## Дальше — Этап 6

Модуль `sync/` в десктопе: поиск/создание спортсмена против центральной
базы вместо локального ввода ФИО (см. ARCHITECTURE.md §7).

---

## Этап 6 — Sync-эндпоинты для десктопа (реальное время) (готово)

Добавлено под `/api/v1/sync/*` (все — только по `X-Sync-Token`):

- `GET /sync/athletes/search?q=&club=` + `POST /sync/athletes` — поиск/создание
  спортсмена (find-or-create клуба по имени заодно).
- `POST /sync/competitions` — создаёт черновик (`status=draft`), best-effort
  сопоставляет `location_name` с существующим городом.
- `POST /sync/competitions/{id}/categories` — категория турнира.
- `POST /sync/competitions/{id}/participants` — регистрация участника
  (ссылается на центрального `athlete_id`).
- `POST /sync/matches` + `PATCH /sync/matches/{id}` — матч по ходу сетки.
- `POST /sync/competitions/{id}/publish` — `draft → published` (полный
  пересчёт статистики/рейтингов — Этап 7).

**Важная находка на этом этапе:** десктоп не собирает пол участника.
`athletes.gender` стал nullable (миграция `861d708b8a1a`, CHECK-constraint
смягчён до `gender is null or gender in ('male','female')`) — иначе синк
падал бы на каждом новом спортсмене. См. `desktop-app/README.md` за
рекомендацией на будущее.

### Проверено вживую

Полная цепочка через curl: создание спортсмена → поиск → турнир →
категория → участник → матч — все 6 запросов отработали корректно на
реальной Postgres. Подробный сквозной тест с реальным десктоп-модулем —
см. `desktop-app/README.md`.

## Дальше — Этап 7

`publish_pipeline.py` — полноценная публикация турнира: пересчёт
`athlete_statistics` (кроме `is_manual_override`) и `athlete_rankings`/
`club_rankings` при публикации (см. ARCHITECTURE.md §7).
