# Atyrau Armsport — Frontend (Этап 4)

React + TypeScript + Vite + Tailwind CSS v4. Публичный сайт федерации,
читает только `/api/v1/public/*` из FastAPI (см. `ARCHITECTURE.md`).

## Запуск

```bash
npm install
cp .env.example .env      # укажите VITE_API_BASE_URL, если бэкенд не на localhost:8000
npm run dev
```

Бэкенд (stage 3) должен быть поднят отдельно и слушать `/api/v1/public/*`
с `CORS allow_origins` для `http://localhost:5173` (сейчас `*`, см.
`backend/app/main.py`).

## Что входит в Этап 4

Из таблицы §7 ARCHITECTURE.md: «React-скелет: Home, Athletes, AthleteProfile,
Competitions на публичном API — страницы открываются в браузере, фильтры
работают».

Реализовано:

- **Home** — витрина: последние опубликованные турниры + тизер спортсменов.
- **Athletes** — список с фильтрами (имя, пол, разряд) и пагинацией,
  фильтры/страница синхронизированы с URL (`?name=&gender=&rank=&page=`).
- **AthleteProfile** — карточка спортсмена, циферблат win-rate (сигнатурный
  элемент айдентики), история турниров, история матчей.
- **Competitions** — список с фильтром по году и пагинацией.
- **CompetitionDetail** — добавлено сверх минимума ради целостности ссылок
  (профиль спортсмена ссылается на турнир, турнир — на результаты и профили
  участников). Использует `GET /competitions/{id}` и `GET
  /competitions/{id}/results`.

Всё читается через типизированные хуки в `src/features/*`
(`@tanstack/react-query`) поверх тонкого клиента `src/lib/api.ts`.

## Дизайн-система

Токены — `src/styles/tokens.css` (Tailwind v4 `@theme`). Айдентика: приборная
панель буровой на Каспии — циферблат-манометр как сигнатурный элемент
(`src/components/ui/Gauge.tsx`), клёпаные разделители (`.rivet-line`),
шрифты Unbounded / IBM Plex Sans / IBM Plex Mono.

## Известные ограничения этого этапа

- `/public/home/summary` описан в ARCHITECTURE.md §4.1, но не реализован в
  backend stage 3 — Home-страница поэтому собирает сводку сама из
  `/public/competitions` + `/public/athletes` (см. комментарий в `lib/api.ts`).
  Когда эндпоинт появится на бэке, замена — один вызов.
- Auth/админка сайта (Этап 5), sync-модуль десктопа (Этап 6),
  publish-pipeline (Этап 7), рейтинги (Этап 8), медиа (Этап 9) — не входят
  в этот этап согласно §7.
