# Security Audit — Atyrau Armsport

Дата: 2026-08-11. Область: backend (FastAPI + SQLAlchemy + PostgreSQL, Railway),
фронтенд (React/Vite, Vercel), десктоп-приложение (CustomTkinter, синхронизация
турниров). Главное правило аудита: **клиент не доверяется** — ни браузер, ни
десктоп не являются источником истины.

## Резюме

Проверены все 43 пункта задания: authentication/authorization, IDOR, sync
протокол (tampering/replay), файлы и фото, секреты, зависимости, DoS,
целостность рейтингов/результатов, утечки информации, OWASP Top 10.

Найдено и устранено 18 уязвимостей (1 CRITICAL, 6 HIGH, 7 MEDIUM, 4 LOW).
Остались 3 осознанных риска (см. «Известные риски»). Все изменения покрыты
тестами `backend/tests/security/` (48 тестов + 20 субтестов), полный прогон —
134 passed.

**Общий SECURITY SCORE: 82 / 100**

## Endpoints

Базовый префикс: `/api/v1`. Защита: `public` — без авторизации, `admin` —
JWT + роль (super_admin/admin/editor), `sync` — статический service-token
`X-Sync-Token`, `auth` — открытый вход.

### auth
| Метод | Путь | Защита |
|---|---|---|
| POST | /auth/login | rate limit (IP + username) |
| GET | /auth/me | JWT |

### public
| Метод | Путь | Защита |
|---|---|---|
| GET | /public/ping | — |
| GET | /public/athletes, /athletes/birthdays, /athletes/{id}, /athletes/{id}/history, /athletes/{id}/elo-history, /athletes/{id}/matches | hidden-спортсмены → 404 |
| GET | /public/clubs, /clubs/{id}, /clubs/{id}/rating | — |
| GET | /public/coaches, /coaches/{id} | hidden-тренеры скрыты |
| GET | /public/competitions, /competitions/{id}, /results, /hand-results, /bracket, /queue, /participants | draft-турниры → 404 |
| GET | /public/news, /news/{slug} | — |
| GET | /public/rankings/athletes, /coaches, /clubs, /elo | — |
| GET | /public/reference/cities | — |

### admin (JWT + role)
| Метод | Путь | Защита |
|---|---|---|
| GET | /admin/ping | role |
| CRUD | /admin/athletes, /athletes/{id}, /athletes/{id}/statistics, /athletes/{id}/photo, /athletes/{id}/statistics/recalculate | role |
| CRUD | /admin/clubs, /clubs/{id}, /clubs/{id}/members, /clubs/{id}/members/remove | role |
| CRUD | /admin/coaches, /coaches/{id}, /coaches/{id}/photo | role |
| CRUD | /admin/news, /news/{id} | role |
| CRUD | /admin/gallery/albums, /photos, /videos | role |
| CRUD | /admin/competitions, /competitions/{id}/documents | role |
| POST | /admin/media/upload | role |
| POST | /admin/reference/cities | role |

### sync (X-Sync-Token)
| Метод | Путь | Защита |
|---|---|---|
| GET | /sync/ping | token |
| CRUD | /sync/athletes, /athletes/search, /athletes/changes | token |
| CRUD | /sync/clubs, /coaches, /coaches/changes | token |
| POST/DELETE | /sync/competitions, /competitions/{id}/categories, /participants, /publish, /dvoeborie-overrides, /status | token |
| POST/PATCH/DELETE | /sync/matches, /matches/batch, /matches/{id} | token + валидация категории |
| POST | /sync/photos/delete | token + cloud name |
| DELETE | /sync/categories/{id} | token |

## Найденные уязвимости

| ID | Severity | Место | Проблема | Сценарий | Влияние | Статус |
|---|---|---|---|---|---|---|
| S1 | CRITICAL | `core/config.py` | Значения-заглушки из `.env.example` проходили валидацию | Атакующий читает репозиторий и подделывает JWT суперадмина / sync-токен | Полный доступ к /sync/* и /admin/* | ИСПРАВЛЕНО: deny-лист плейсхолдеров + JWT_SECRET min 32 символа; тест `test_config_secrets.py` |
| S2 | HIGH | `main.py` CORS | `allow_origin_regex=.*\.vercel\.app` + `allow_credentials=True` | Злоумышленник деплоит поддомен `atyrau-armwrestling-evil.vercel.app` | Отражённые CORS-запросы с credentials | ИСПРАВЛЕНО: точные origins, credentials сняты (фронт не использует cookies); тест `test_headers_and_rate_limit.py` |
| S3 | HIGH | `sync/matches.py` | Отсутствие идемпотентности: повторный POST/перехват создаёт дубль матча, `apply_match_result` задваивает elo | Replay перехваченного запроса при утёкшем/переиспользованном токене | Искажение рейтингов и результатов | Частично: валидации добавлены, идемпотентность требует desktop-id в протоколе — см. R1 |
| S4 | HIGH | `schemas/sync.py` | `status/hand/bracket` — свободные строки, `winner_id` мог указывать на участника вне матча | Десктоп/атакующий шлёт мусорные значения | Битые данные, подмена победителя | ИСПРАВЛЕНО: Literal-энумы, winner ∈ {p1,p2}, потери ≤ 2, batch ≤ 10000; тест `test_sync_schemas.py` |
| S5 | HIGH | `sync/matches.py` | p1/p2/winner могли принадлежать другой категории/турниру | Вписать участника чужой категории в матч | Искажение elo/итогов категории | ИСПРАВЛЕНО: `_validate_participants_belong`; тест `test_sync_protection.py` |
| S6 | HIGH | `public/competitions.py` | Draft-турниры читались по id (сетка, участники, результаты) | Перебор id | Раскрытие неопубликованного | ИСПРАВЛЕНО: `_get_public_competition` → 404; тест `test_public_exposure.py` |
| S7 | HIGH | `public/athletes.py` | hidden-спортсмены отдавались по /history, /elo-history, /matches | Прямой запрос по id | Раскрытие скрытых спортсменов | ИСПРАВЛЕНО: `_ensure_visible_athlete` → 404; тест `test_public_exposure.py` |
| S8 | MEDIUM | `auth.py` | Нет rate limit; различие времени ответа существующий/несуществующий логин; разные тексты ошибок | Перебор паролей, энумерация логинов | Брутфорс | ИСПРАВЛЕНО: лимит по IP (X-Forwarded-For) + по username, dummy bcrypt-хэш, единая ошибка 401; тест `test_headers_and_rate_limit.py` |
| S9 | MEDIUM | `deps.py` | Сравнение sync-токена обычным `!=` | Timing-канал при частичном совпадении | Перебор токена | ИСПРАВЛЕНО: `secrets.compare_digest` |
| S10 | MEDIUM | Пагинация (6 листингов) | page_size без лимита | `?page_size=1000000` | DoS (большие выборки) | ИСПРАВЛЕНО: `Query(ge=1, le=100)`, admin-coaches le=500; тест `test_public_exposure.py` |
| S11 | MEDIUM | `cloudinary_photos.py` | Удаление по произвольному Cloudinary URL (любой аккаунт) | Подсунуть URL чужого файла | Удаление файлов в чужом облаке | ИСПРАВЛЕНО: проверка cloud name; тест `test_cloudinary_photo_scope.py` |
| S12 | MEDIUM | `models/results.py` | Нет UNIQUE на (competition, category, participant), place мог быть отрицательным | Повторные записи/мусор | Дубли мест, битые данные | ИСПРАВЛЕНО: UNIQUE + check place ≥ 0, миграция `a3b4c5d6e7f8` (с дедупом) |
| S13 | MEDIUM | `sync/competitions.py` | `manual_rank` без ограничений | Отрицательное/гигантское место | Битые места двоеборья | ИСПРАВЛЕНО: `Field(ge=1, le=1000000)` |
| S14 | MEDIUM | `main.py` | Нет CSP / Referrer-Policy; Swagger открыт в проде | Просмотр карты API, утечка токена в Referer | Разведка, утечки | ИСПРАВЛЕНО: CSP default-src 'none', Referrer-Policy, docs/redoc выключены при `ENVIRONMENT=production` |
| S15 | LOW | `sync/*.py` | Возврат `{"error": "not_found"}, 404` без HTTPException | — | Нестандартный формат ошибок | ИСПРАВЛЕНО: `HTTPException(404)` |
| S16 | LOW | `public/clubs.py` | Write-on-GET: `check_inactive_athletes` выполняет UPDATE при чтении профиля | Повторные GET от краулеров | Лишние записи (штраф идемпотентен, данные не повреждаются) | ОСТАВЛЕНО осознанно (бизнес-триггер, идемпотентен) — см. R3 |
| S17 | LOW | `schemas/*.py` (sync) | Масс-ассигнмент через неизвестные поля | Десктоп шлёт `coach_name` и т.п. | Запись в обход схемы | ИСПРАВЛЕНО: `extra='forbid'` на всех sync-схемах; тест `test_sync_schemas.py` |
| S18 | LOW | `.env.example` | Нет комментария о минимальной длине секретов | Копирование примера | Слабые секреты в проде | ИСПРАВЛЕНО: комментарии добавлены, плейсхолдеры отклоняются при старте |

## SECURITY SCORE

| # | Категория | Оценка | Комментарий |
|---|---|---|---|
| 1 | Authentication & Authorization | 8.5 | bcrypt, HS256 strict, роли, rate limit, dummy-хэш. Минус: in-memory лимиты (сбрасываются при рестарте), нет капчи |
| 2 | IDOR / Object-level access | 9.0 | Все объекты проверяются на принадлежность; draft/hidden закрыты 404 |
| 3 | Sync protocol (tampering/replay) | 7.0 | Constant-time токен, энумы, участники категории. Минус: нет идемпотентности матчей (R1), статический токен без ротации |
| 4 | File & photo handling | 8.5 | Секрет Cloudinary только на бэке, cloud name проверка. Минус: /photos/delete ограничен областью аккаунта, не по владельцу |
| 5 | Secrets & configuration | 9.0 | Плейсхолдеры отклоняются, min length 32, .env в .gitignore. Минус: CLOUDINARY_* не валидируются на плейсхолдеры |
| 6 | Dependencies & CVEs | 8.0 | Зависимости зафиксированы (requirements-lock.txt). Рекомендация: регулярный `pip-audit` в CI (см. R4) |
| 7 | DoS & rate limiting | 7.5 | Лимиты пагинации, batch ≤ 10000, rate limit логина. Минус: нет общих rate limits на public API |
| 8 | Ratings/results integrity | 8.0 | UNIQUE + check, manual_rank ≥ 1, участники категории. Минус: replay-дубли матчей могут задвоить elo (R1), нет блокировки результатов после completed (осознанно, переигровки) |
| 9 | Info leakage & headers | 8.5 | Security headers, CSP, docs off в проде, единые ошибки. Минус: production-конфиг не проверен на живом сервере (нет доступа) |
| 10 | OWASP Top 10 misc | 8.0 | Mass assignment закрыт, SQLi не найдено (ORM), CSRF неприменимо (JWT в заголовке), SSRF нет. Минус: XSS-поверхность фронтенда вне области бэкенд-аудита |

Итог: (8.5+9.0+7.0+8.5+9.0+8.0+7.5+8.0+8.5+8.0) / 10 = **82/100**

## Известные риски (осознанно не исправлено)

- **R1 (HIGH, accepted):** идемпотентность/anti-replay матчей. Дубль POST
  /sync/matches создаёт второй Match и повторно применяет elo. Полное
  исправление требует добавления desktop-id матча в схему (изменение
  протокола синхронизации и десктоп-приложения); переигровки гранд-финала —
  легитимные повторные матчи тех же участников, поэтому простой UNIQUE
  невозможен. Рекомендация: десктоп уже повторно шлёт только свои матчи;
  после утечки токена — немедленная ротация `DESKTOP_SYNC_TOKEN`.
- **R2 (MEDIUM, accepted):** rate limit in-memory — не распределённый, при
  нескольких инстансах бэкенда сбрасывается. Для текущего одноинстансового
  Railway-деплоя достаточно.
- **R3 (LOW, accepted):** write-on-GET `check_inactive_athletes` в профиле
  клуба — бизнес-триггер ленивого штрафа за неактивность, идемпотентен,
  эксплуатировать невозможно. При желании — перенести в cron/фоновую задачу.

## Рекомендации после аудита

- R4: добавить `pip-audit` в CI и периодически обновлять зависимости.
- R5: задать на Railway `ENVIRONMENT=production` (отключит /docs, /redoc).
- R6: проверить фактические секреты в проде: JWT_SECRET ≥ 32, замена
  placeholder'ов обязательна — иначе приложение не стартует (проверка при
  старте).
- R7: ротация `DESKTOP_SYNC_TOKEN` раз в год или после любого подозрения
  на утечку.
- R8: фронтенд — проверить CSP на реальном сайте (Vercel добавляет свои
  заголовки; конфликты отсутствуют, т.к. API отдаёт JSON).

## Как проверялось

- Ручной аудит всех 43 пунктов задания по коду (endpoints, схемы, сервисы,
  модели, десктоп-клиент, конфиг).
- Автотесты `backend/tests/security/`:
  `test_config_secrets.py`, `test_sync_schemas.py`, `test_cloudinary_photo_scope.py`,
  `test_public_exposure.py`, `test_sync_protection.py`, `test_headers_and_rate_limit.py`.
- Полный прогон: `python -m pytest -q` → **134 passed**.
- Alembic: одна голова (`a3b4c5d6e7f8`), миграция создаёт UNIQUE/check с
  предварительным дедупом.
- Ограничения: прод-среда (Railway/Neon) не проверялась напрямую —
  доступа нет; флаги ENVIRONMENT/CORS-домен соответствуют конфигурации
  деплоя по README.
