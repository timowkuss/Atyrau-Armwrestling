# ПОЛНЫЙ АУДИТ ПРОЕКТА: Atyrau Armsport (Armwrestling Federation)

**Дата:** 2026-07-29  
**Тип аудита:** Статический анализ кода (Full Code Review)  
**Объём:** ~15 000 строк Python, ~6 000 строк TypeScript/TSX  

---

## Содержание

1. [🔴 Critical](#1--critical)
2. [🟠 High](#2--high)
3. [🟡 Medium](#3--medium)
4. [🟢 Low](#4--low)
5. [Оценка по критериям](#5-оценка-по-критериям)
6. [Стратегия тестирования](#6-стратегия-тестирования)

---

# 1. 🔴 Critical

## C1. Production DB credentials в `.env` + default JWT secret + default sync token

**Файлы:** `backend/.env`, `backend/app/core/config.py:12,18`  
**Описание:** В `.env` лежит живая строка подключения к NeonDB (пароль `npg_FGiD57qoagUx`). При этом `JWT_SECRET` и `DESKTOP_SYNC_TOKEN` НЕ переопределены в `.env` — используются хардкодные значения `"change-me-in-production"` и `"change-me-desktop-sync-token"`.  

**Воспроизведение:** Любой, кто знает эти дефолтные значения, может:  
- подделать JWT и войти как `super_admin`  
- отправить запрос с `X-Sync-Token: change-me-desktop-sync-token` и получить полный write-доступ ко всем данным  

**Исправление:**  
1. Сменить пароль NeonDB  
2. Установить `JWT_SECRET` и `DESKTOP_SYNC_TOKEN` в production-окружении  
3. В `config.py` сделать значения `""` (пустая строка) и добавить проверку `if not self.JWT_SECRET: raise RuntimeError("JWT_SECRET not set")` при старте  

---

## C2. Хардкодный API-токен десктопа в `sync_config.json` и `check_backend.py`

**Файлы:** `desktop-app/sync_config.json:3`, `desktop-app/check_backend.py:3`  
**Значение:** `Timowkuss`  
**Описание:** Токен для продакшен-сервера (`atyrau-armwrestling-production.up.railway.app`) хардкодом лежит в репозитории.  

**Воспроизведение:** `git clone` → `cat sync_config.json` → токен скомпрометирован.  

**Исправление:**  
- Немедленно ротировать токен на сервере  
- Удалить токен из `sync_config.json`, читать из переменной окружения  
- `check_backend.py` удалить из репозитория  

---

## C3. N+1 запросов в `public/athletes.py:get_athlete` — 7 SQL на один профиль

**Файл:** `backend/app/api/v1/public/athletes.py:105-160`  
**Описание:** Для отображения карточки одного спортсмена выполняется 7 отдельных запросов к БД:  
1. `Athlete`  
2. `AthleteStatistic`  
3. `City` (ленивая загрузка)  
4. `Club.name` (ленивая загрузка)  
5. `Coach.full_name` (ленивая загрузка)  
6. `Region`  
7. `Country`  

При 1000 RPM это 7000 запросов/сек.  

**Исправление:** Использовать `joinedload()` для всех relation в первом запросе:  
```python
athlete = (
    db.query(Athlete)
    .options(
        joinedload(Athlete.club),
        joinedload(Athlete.coach),
        joinedload(Athlete.statistics),
        joinedload(Athlete.city),
    )
    .filter(...)
    .first()
)
```

---

## C4. N+1 запросов в `public/athletes.py:get_athlete_matches` — 3 SQL на матч

**Файл:** `backend/app/api/v1/public/athletes.py:200-242`  
**Описание:** Для каждого матча в истории спортсмена делается 3 отдельных `db.get(CompetitionParticipant, ...)`. При 50 матчах → 150 лишних запросов.  

**Исправление:** Собрать все `p1_id/p2_id/winner_id`, загрузить одним `IN`-запросом с `joinedload(CompetitionParticipant.athlete)`.  

---

## C5. SQL-инъекция через f-строку в `UPDATE matches`

**Файл:** `desktop-app/armwrestling_tournament.py:1517,2191`  
**Код:** `self.db.conn.execute(f"UPDATE matches SET {col}=? WHERE id=?", (player_id, match_id))`  
**Описание:** Имя колонки интерполируется через f-строку. Сейчас вызывается только с `"p1_id"/"p2_id"`, но паттерн опасен.  

**Исправление:** Добавить whitelist:  
```python
ALLOWED = {"p1_id", "p2_id"}
if col not in ALLOWED:
    raise ValueError(f"Недопустимая колонка: {col}")
```

---

## C6. Гонка в `on_bracket_reset` — drain `_sync_queue` не атомарен

**Файл:** `desktop-app/sync/sync_manager.py:675-686`  
**Описание:** Пока UI-поток дренирует очередь (drain → filter → reput), `dispatch_match_update_async` может добавить новый элемент, который:  
- не попадёт в drained (уже после get_nowait)  
- не будет отфильтрован  
- уйдёт в очередь как stale `update_match` для удалённого mid  

**Воспроизведение:** Сканер считывает штрихкод (→ `_sync_match` → `put` в очередь) в момент, когда `on_bracket_reset` уже проверил `empty()` но ещё не закончил reput.  

**Исправление:** Убрать drain полностью — вместо этого проверять в `_sync_worker_loop`, есть ли mid в наборе `_reset_mids`:  
```python
# on_bracket_reset:
self._reset_mids.update(reset_mids)
# _sync_worker_loop:
if mid in self._reset_mids:
    self._reset_mids.discard(mid)
    continue  # пропускаем stale update_match
```

---

# 2. 🟠 High

## H1. Нет rate limiting на `/auth/login`

**Файл:** `backend/app/api/v1/auth.py:13-26`  
**Severity:** Высокий — брутфорс паролей без ограничений.  
**Исправление:** `slowapi` + `@limiter.limit("5/minute")`.  

---

## H2. Mass assignment через `setattr` в админке и sync

**Файлы:** `admin/athletes.py:99-100`, `sync/matches.py:53-54`, `sync/athletes.py:233-234`, `sync/coaches.py:203-204`  
**Описание:** `for field, value in data.items(): setattr(model, field, value)` — если в Pydantic schema добавится поле вроде `role_id` или `is_admin`, оно молча запишется.  
**Исправление:** Явное маппинг полей или использовать `UPDATE` с фиксированным набором колонок.  

---

## H3. Нет HTTP Security Headers

**Файл:** `backend/app/main.py`  
**Описание:** Отсутствуют `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `Content-Security-Policy`.  
**Исправление:** Middleware:  
```python
response.headers["X-Content-Type-Options"] = "nosniff"
response.headers["X-Frame-Options"] = "DENY"
response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```

---

## H4. Cloudinary error — утечка информации

**Файл:** `backend/app/api/v1/admin/media.py:67`  
**Код:** `detail=f"Cloudinary: {e}"` — сырая ошибка Cloudinary уходит клиенту.  
**Исправление:** Логировать `e`, в ответ отдавать `"Ошибка загрузки файла"`.  

---

## H5. Нет уникальности на `athletes (full_name, birth_date)` — дубли при параллельных sync

**Файл:** `backend/app/db/models/athletes.py:37`  
**Описание:** Две concurrent синхронизации могут создать двух спортсменов с одинаковым ФИО + датой рождения.  
**Исправление:** `UniqueConstraint("full_name", "birth_date")`.  

---

## H6. Нет индекса на `athletes.full_name` для `ilike`-поиска

**Файл:** `backend/app/db/models/athletes.py:37`  
**Severity:** На 10k записей каждый `ilike` — sequential scan.  
**Исправление:** `CREATE INDEX ix_athletes_full_name_trgm ON athletes USING gin (full_name gin_trgm_ops)`.  

---

## H7. Нет индекса на `coaches.full_name`

**Файл:** `backend/app/db/models/coaches.py:15`  
**Аналогично H6.**  

---

## H8. Хардкодный пароль удаления `"1234"`

**Файл:** `desktop-app/armwrestling_tournament.py:79`  
**Код:** `DELETE_ATHLETE_PASSWORD = "1234"`  
**Воспроизведение:** Любой может удалить спортсмена, введя `1234`.  
**Исправление:** Убрать пароль (single-user desktop) или использовать нормальную аутентификацию.  

---

## H9. `flush_pending` читает входящие данные один раз и процесссит stale

**Файл:** `desktop-app/sync/sync_manager.py:814-818`  
**Описание:** `pending()` вызывается один раз на проход → snapshot. Если между строкой 1 и строкой 50 другой thread вызвал `_self_heal_missing_tournament`, строки 10-20 могут быть уже удалены. `exists()` проверяет каждую, но если строку удалили и создали заново (с тем же id — невозможно для AUTOINCREMENT, но возможно при truncate), данные могут быть stale.  
**Исправление:** Минорно — уже защищено `exists()` check.  

---

## H10. Connection pool без явной конфигурации

**Файл:** `backend/app/db/session.py:6-13`  
**Описание:** `create_engine` без `pool_size` и `max_overflow` → SQLAlchemy defaults: pool_size=5, max_overflow=10. Под нагрузкой 100+ concurrent requests соединения закончатся за секунды.  
**Исправление:**  
```python
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
)
```  

---

## H11. `_flush_thread_running` TOCTOU race

**Файл:** `desktop-app/sync/sync_manager.py:162-170`  
**Описание:** Два потока могут одновременно увидеть `_flush_thread_running == False` и запустить два `flush_pending`.  
**Исправление:** Захватывать `_flush_lock` вокруг check-then-set.  

---

## H12. Потеря данных при `db.conn` swap во время генерации сетки

**Файл:** `desktop-app/armwrestling_tournament.py:1090-1099`  
**Описание:** `db.conn` заменяется на `_BatchConnProxy`, чей `commit()` — no-op. Если в это время другой callback попытается записать в БД, данные потеряются.  
**Исправление:** Re-entrant lock или context manager.  

---

## H13. Desktop `matches.p1_id/p2_id/winner_id` без FK

**Файл:** `desktop-app/armwrestling_tournament.py:322-343`  
**Описание:** Только `tournament_id` и `category_id` имеют FOREIGN KEY. Колонки `p1_id`, `p2_id`, `winner_id` — голые INTEGER без ссылочной целостности.  
**Исправление:** Добавить `FOREIGN KEY (p1_id) REFERENCES participants(id) ON DELETE SET NULL`.  

---

## H14. Индивидуальные `commit()` на каждый `_set_links` при генерации сетки

**Файл:** `desktop-app/armwrestling_tournament.py:1490`  
**Описание:** Для 80 матчей double-elimination — 80 отдельных `commit()` в SQLite.  
**Исправление:** Вынести `commit()` за цикл.  

---

# 3. 🟡 Medium

| ID | Файл | Описание | Исправление |
|----|------|----------|-------------|
| M1 | `backend/.../public/competitions.py:80` | N+1 на `competition.categories` — ленивая загрузка | `.options(joinedload(Competition.categories))` |
| M2 | `backend/.../matches.py:29` | Нет CHECK на `hand` (`'Правая'/'Левая'/'Обе'`) | `CheckConstraint(...)` |
| M3 | `backend/.../competitions.py:47-48` | Нет CHECK на `bracket_system`, `format_type` | `CheckConstraint(...)` |
| M4 | `backend/.../coaches.py:15` | Нет UNIQUE на `coaches.full_name` | `UniqueConstraint(...)` |
| M5 | `backend/.../results.py:20` | Нет индекса на `results.competition_id` | `Index(...)` |
| M6 | `desktop/...py:306` | `participants.category_id` FK без ON DELETE | `ON DELETE CASCADE` |
| M7 | `desktop/...py:419` | `participants.athlete_id` FK без ON DELETE | `ON DELETE SET NULL` |
| M8 | `desktop/...py:423` | `athletes.coach_id` FK без ON DELETE | `ON DELETE SET NULL` |
| M9 | `desktop/...py:629-634` | Нет индекса на `participants.tournament_id` и `category_id` | `CREATE INDEX` |
| M10 | `backend/.../main.py:27-28` | CORS: `allow_methods=["*"]`, `allow_headers=["*"]` | Ограничить конкретными значениями |
| M11 | `backend/.../auth.py:19-26` | Нет блокировки после N неудачных попыток логина | `failed_login_attempts` + lockout |
| M12 | `backend/.../security.py:20-36` | JWT токены нельзя отозвать до истечения 12ч | Token version в БД |
| M13 | `backend/.../users.py:22-38` | User model: нет `last_login`, `failed_attempts`, `token_version` | Добавить поля |
| M14 | `desktop/...py:1288,1338` | Дублирующийся вызов `_compute_and_apply_is_bye` | Убрать вызов на line 1288 |
| M15 | `desktop/...py:4481` | `nonlocal edit_id` переприсваивает параметр функции | Использовать mutable container |
| M16 | `desktop/...py:1092-1099` | `force_queue` toggle не re-entrant | Сделать counter |
| M17 | `desktop/...py:5045-5056` | Фото участников не загружаются в Cloudinary | Использовать `cloudinary_client.upload_photo` |
| M18 | `desktop/...py:2627-2628` | Stale cache window на 250ms после скана | Вызывать `_load_bracket()` синхронно |
| M19 | `desktop/...py:2901-2904` | `on_bracket_reset` дёргается дважды (reset+generate) | Проверять флаг `_already_reset` |
| M20 | `backend/.../competitions.py:30` | Статусы `competitions` не совпадают: desktop `'active'` vs backend `'published'` | Проверить sync-маппинг |
| M21 | `backend/.../athletes.py:39` | Gender: desktop `'M'/'F'`, backend `'male'/'female'` | Унифицировать или убедиться что `_normalize_gender` всегда вызывается |
| M22 | `desktop/sync/state.py:35` | `check_same_thread=False` на sync_state.db — есть `_lock`, безопасно | ОК, мониторить |
| M23 | `desktop/...py:all sync wrappers` | `except Exception` в каждом sync-wrapper — silent fail | Показывать UI-индикатор ошибки синхронизации |

---

# 4. 🟢 Low

| ID | Файл | Описание |
|----|------|----------|
| L1 | `backend/.../config.py:13` | JWT алгоритм HS256 (symmetrical) — приемлемо для MVP, но RS256 надёжнее |
| L2 | `backend/.../config.py:14` | ACCESS_TOKEN_EXPIRE=12ч — долго, рекомендуется 2ч + refresh token |
| L3 | `desktop/...py:96,98` | Тройной импорт `OrderedDict` (дубли) |
| L4 | `desktop/...py:245,249,251` | `is` vs `==` для строк — сейчас безопасно, но хрупко |
| L5 | `desktop/...py:25-27` | `print()` вместо `logging` — логи теряются при запуске `.exe` |
| L6 | `backend/.../sync/matches.py:53-54` | `setattr` для update_match — надо следить чтобы schema и model не расходились |
| L7 | `desktop/check_stale_queue.py:30` | SQL injection via f-string in diagnostic script (хардкод, но паттерн опасен) |
| L8 | `backend/.../sync/categories.py:25-28` | `synchronize_session=False` — ORM session может иметь stale объекты |
| L9 | `desktop/...py:4691-4695` | Вес категории по умолчанию 0 при ошибке парсинга |
| L10 | `desktop/...py:1510-1519` | Индивидуальный commit на каждый `_place_player` |
| L11 | `desktop/...py:1558-1588` | `_resolve_all_byes` может делать до 50 итераций |
| L12 | `frontend/vercel.json` | SPA rewrites — если нет fallback, 404 на глубокие ссылки |
| L13 | `backend/Procfile` | `alembic upgrade head` на каждый деплой — ок, но при ошибке миграции сайт не стартует |
| L14 | `frontend/src/...` | Нет обработки ошибок React Query на уровне глобального `onError` |

---

# 5. Оценка по критериям

| Критерий | Оценка (1-10) | Комментарий |
|----------|:------------:|-------------|
| **Архитектура** | 8 | Чёткое разделение Desktop ↔ Backend ↔ Frontend. Sync слой спроектирован грамотно (offline-first, multi-pass replay, self-heal). Единственный минус — нет брокера сообщений для гарантированной доставки. |
| **Качество кода** | 7 | Хороший Python (type hints, comprehensions). Но: хардкодные секреты, `print()` вместо logging, `except Exception` в ~30 местах, отсутствие тестов. |
| **Производительность** | 4 | N+1 запросы на публичных эндпоинтах (критично для масштаба). Нет индексов на `full_name` для поиска. Connection pool не настроен. Индивидуальные `commit()` в SQLite. |
| **Безопасность** | 3 | 6 CRITICAL findings: дефолтные секреты в production, хардкодный API-токен, SQL injection, пароль `1234`, отсутствие rate limiting и security headers. |
| **UX** | 7 | Desktop UI понятный, поддержка сканера, тёмная тема, live табло. Минусы: silent sync failures, нет индикации загрузки/ошибки. |
| **UI** | 8 | CustomTkinter выглядит современно. Bracket rendering через Canvas красивый. Scrollable для больших сеток. |
| **Надёжность** | 5 | Sync имеет self-heal, но гонки в `_sync_queue`, TOCTOU в `_flush_thread_running`, и `_BatchConnProxy` могут привести к потере данных. Offline-режим работает, но нет тестов сценариев обрыва соединения. |
| **Масштабируемость** | 4 | N+1 запросы убьют БД при 1000+ RPM. Connection pool не настроен. Desktop — single-user. Frontend — CDN-static, ок. |
| **Готовность к продакшену** | 4 | Без исправления 6 CRITICAL findings выпускать нельзя. После исправления C1-C6, H1-H4 — можно, но под нагрузкой вскроются проблемы производительности. |

## Итого: **5.4 / 10**

---

# 6. Стратегия тестирования

## Unit-тесты (что нужно покрыть в первую очередь)

| Модуль | Что тестировать | Почему важно |
|--------|----------------|--------------|
| `elo_engine.py` | Расчёт Elo для победителя/проигравшего, BYE-фильтрация | Ошибка в Elo — неправильные рейтинги тысяч спортсменов |
| `sync/api_client.py` | Каждый HTTP-метод с mock-сервером, обработка 404/500/timeout | Синхронизация не должна падать на временных ошибках сети |
| `sync/state.py` | `enqueue`-`pending`-`mark_done`-`purge_pending` | Целостность офлайн-очереди |
| `sync_manager.py` | `_replay` для каждой операции (9 штук) | Ни одна операция не должна блокировать очередь навсегда |
| `engine` (Single/Double Elimination) | `advance_winner`, `_propagate`, `_resolve_all_byes` | Правильность турнирной сетки — краеугольный камень |
| `Database` | CRUD всех таблиц, get_matches, get_participants | Без тестов БД любое schema change — риск |

## Integration-тесты

| Сценарий | Описание |
|----------|----------|
| Sync round-trip | Desktop создаёт турнир → sync → Backend GET → данные совпадают |
| Offline queue | Отключить сеть → создать турнир, категории, участников, матчи → включить сеть → flush → всё синхронизировалось |
| Bracket reset + generate | Сбросить сетку → сгенерировать новую → sync → сервер не имеет старых матчей и имеет новые |
| Concurrent sync | Два десктопа одновременно синхронизируют данные в один backend |

## E2E-тесты

| Сценарий | Инструмент |
|----------|-----------|
| Desktop: создать турнир → заполнить → сгенерировать сетку → провести матчи → синхронизировать | PyAutoGUI / Playwright (Windows) |
| Frontend: открыть сайт → найти спортсмена → посмотреть профиль, историю, рейтинг | Playwright |
| Admin: логин → CRUD спортсмена/клуба/тренера/новости → загрузить фото | Playwright |

## Load-тесты

| Сценарий | Инструмент | Метрики |
|----------|-----------|---------|
| GET `/public/athletes?search=...` — 1000 RPM, 2 мин | Locust | p95 < 500ms, no errors |
| GET `/public/competitions/{id}/board` — 500 RPM | Locust | p95 < 1s |
| POST `/sync/athletes` — 100 concurrent | Locust | no duplicates, no 409 |
| `flush_pending` — 1000 offline операций | Юнит-тест | все выполнены за < 5 проходов |

## Security-тесты

| Тест | Инструмент | Что проверяет |
|------|-----------|---------------|
| SQL injection на всех endpoints с sync/admin/public | sqlmap / manual | Все параметры, включая `full_name`, `hand`, `sort_by` |
| XSS на всех текстовых полях (news, bio, description) | manual | `<script>alert(1)</script>` — stored XSS |
| JWT forge с алгоритмом `none` | manual | `alg: "none"` — python-jose уязвим? |
| Rate limit bypass | wrk / bombardier | Многократные POST `/auth/login` |
| IDOR на admin endpoints | manual | `/admin/athletes/{id}` с чужим id |

## Smoke-тесты (перед каждым деплоем)

```bash
# Backend
curl -f http://localhost:8000/health
curl -f http://localhost:8000/api/v1/public/ping
curl -f -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"test"}'

# Desktop
python -c "from armwrestling_tournament import Database; db = Database(); print('DB OK', db.conn.execute('SELECT COUNT(*) FROM tournaments').fetchone())"

# Frontend
npm run build && npm run preview  # opens at localhost:5173
```

---

*Аудит проведён статическим анализом кода. Некоторые проблемы (гонки, производительность под нагрузкой) требуют динамического тестирования для подтверждения.*
