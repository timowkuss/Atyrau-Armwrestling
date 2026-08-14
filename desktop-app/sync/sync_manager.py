"""Оркестрирует синхронизацию действий организатора с центральной БД в
реальном времени (см. ARCHITECTURE.md §5). Вызывается из обёрток над
методами Database (см. правки в armwrestling_tournament.py) — сам НИКОГДА
не бросает исключения наружу настолько, чтобы сломать локальную работу:
любая сетевая ошибка уходит в офлайн-очередь и повторяется позже.
"""

import queue
import sqlite3
import threading
import time
from pathlib import Path

from .api_client import ApiClientError, SyncApiClient, UNSET
from .state import SyncState
from . import config

# armwrestling.db лежит в desktop-app/ (родитель папки sync/) — см. тот же
# путь в armwrestling_tournament.py (DB_PATH).
_TOURNAMENT_DB_PATH = Path(__file__).resolve().parent.parent / "armwrestling.db"


class SyncManager:
    def __init__(self, api_client=None, state=None):
        self.api = api_client or SyncApiClient()
        self.state = state or SyncState()
        self.enabled = config.SYNC_ENABLED
        # Когда True — любая операция сразу уходит в офлайн-очередь без
        # попытки реального HTTP-запроса. Используется десктоп-приложением
        # при массовой генерации сетки (см. generate_bracket в
        # armwrestling_tournament.py): без этого каждый матч сетки — это
        # отдельный блокирующий HTTP-запрос на UI-потоке (до
        # REQUEST_TIMEOUT_SECONDS секунд КАЖДЫЙ при проблемах с сетью),
        # из-за чего окно организатора "замирает" на генерации. Очередь же
        # потом единоразово разгребается в фоновом потоке через
        # flush_pending() — так матчи всё равно долетают до сайта, просто
        # без блокировки интерфейса.
        self.force_queue = False
        self._last_flush_attempt = 0
        self._flush_in_progress = False
        # Backoff периодических попыток: если последний flush_pending() не
        # сделал прогресса (все операции упираются в недоступный сервер),
        # авто-тикер не долбит его каждые ~10с бесконечно, а ждёт
        # _BACKOFF_SECONDS. Как только хоть одна операция доехала или
        # очередь опустела — снова пробуем часто. Сами операции из очереди
        # при этом НЕ выбрасываются и ничего не теряется.
        self._BACKOFF_SECONDS = 60
        self._flush_backoff_until = 0.0
        # Настоящая блокировка на случай, если flush_pending() вызовут
        # из нескольких мест одновременно (фоновый поток после генерации
        # сетки, периодический авто-тик UI, кнопка "Синхронизация") —
        # без неё оба вызова читают одну и ту же офлайн-очередь и оба
        # успевают отправить create_match для одних и тех же матчей до
        # того, как первый пометит их выполненными, что даёт дубли на
        # сервере (см. flush_pending).
        self._flush_lock = threading.Lock()

        # Заблокированные (не долетающие до сервера) операции — в основном
        # delete_*, которые НЕ выбрасываем молча (иначе на сайте остаётся
        # лишняя запись, как было с удалением спортсмена). Здесь они
        # копятся с ошибками для показа пользователю в UI-тикере.
        self._blocked_lock = threading.Lock()
        self.blocked_ops: list[dict] = []

        # ── асинхронный воркер для on_match_updated ──────────────────
        # Раньше движок сетки (advance_winner → _propagate → _place_player
        # → _sync_match) вызывал sync_manager.on_match_updated(...) НАПРЯМУЮ
        # на UI-потоке. on_match_updated при живой сети делает блокирующий
        # HTTP PATCH (до REQUEST_TIMEOUT_SECONDS сек), а при продвижении
        # победителя таких вызовов подряд несколько (сам матч + следующий
        # матч в winners/losers + возможные авто-резолвы BYE) — от этого
        # клик "Победил X" реально подвисал на пару секунд, пока клавиатурный
        # ввод/канвас не могли отрисоваться. Теперь _sync_match кладёт джобу
        # в очередь и сразу возвращает управление; один долгоживущий воркер
        # разбирает очередь строго по порядку (FIFO — важно, чтобы апдейт
        # текущего матча не мог обогнать апдейт следующего) в отдельном
        # потоке, не трогая UI.
        self._sync_queue: "queue.Queue" = queue.Queue()
        self._bracket_reset_mids: set[int] = set()
        self._sync_worker = threading.Thread(
            target=self._sync_worker_loop, daemon=True, name="sync-match-worker"
        )
        self._sync_worker.start()

    def _sync_worker_loop(self):
        while True:
            mid, payload = self._sync_queue.get()
            try:
                if mid == "__call__":
                    payload()
                elif mid in self._bracket_reset_mids:
                    self._bracket_reset_mids.discard(mid)
                else:
                    self.on_match_updated(mid, payload)
            except Exception as e:
                print(f"[sync] async job ({mid}): {e}")
            finally:
                self._sync_queue.task_done()

    def dispatch_match_update_async(self, mid, match: dict):
        """Неблокирующая версия on_match_updated — вызывается из UI-потока
        движком сетки. Сам match-словарь читается из локальной SQLite
        синхронно (это быстро, там нет сети), в очередь уходит уже готовый
        dict, чтобы не держать курсор/соединение между потоками."""
        self._sync_queue.put((mid, dict(match)))

    def dispatch_async(self, fn):
        """Общий неблокирующий диспетчер: кладёт произвольный вызов без
        аргументов в тот же FIFO-воркер, что и dispatch_match_update_async
        (тот же порядок исполнения, тот же поток). Используется там, где
        раньше save_match/on_match_created дёргались напрямую с UI-потока
        (ручное редактирование матча) и подвешивали интерфейс на HTTP."""
        self._sync_queue.put(("__call__", fn))

    def is_online(self) -> bool:
        """Быстрая проверка доступности сервера через ping."""
        try:
            self.api.ping()
            return True
        except Exception:
            return False

    def try_auto_flush(self) -> tuple[int, int] | None:
        """Вызывается из таймера UI. Если есть очередь и прошло достаточно
        времени с последней попытки — пробует отправить. Возвращает
        (succeeded, remaining) или None если пытаться не стоит."""
        import time as _time
        now = _time.time()
        if self.state.pending_count() == 0:
            return None
        if now < self._flush_backoff_until:
            return None
        if now - self._last_flush_attempt < 5:
            return None
        self._last_flush_attempt = now
        # flush_pending() сам себя защищает через _flush_lock (см. ниже),
        # так что если генерация сетки уже гонит очередь в фоновом потоке,
        # этот вызов просто сразу вернёт None вместо дублирования отправки.
        return self.flush_pending()

    def try_auto_flush_async(self) -> bool:
        """Неблокирующая версия try_auto_flush для UI-тикера: та же
        проверка очереди и rate-limit, но сама сетевая часть (HTTP с
        таймаутом до REQUEST_TIMEOUT_SECONDS на вызов) уходит в отдельный
        фоновый поток через _trigger_immediate_flush, чтобы тикер на
        UI-потоке не замирал на недоступном сервере. Возвращает True, если
        отправка запланирована."""
        import time as _time
        now = _time.time()
        if self.state.pending_count() == 0:
            return False
        # Backoff: если последний flush упёрся в недоступный сервер, не
        # долбим его новой попыткой каждые ~10с — ждём _BACKOFF_SECONDS.
        if now < self._flush_backoff_until:
            return False
        if now - self._last_flush_attempt < 5:
            return False
        self._last_flush_attempt = now
        self._trigger_immediate_flush()
        return True

    # Короткие повторы прямо здесь (внутри фонового sync-воркера, поэтому
    # никогда не подвешивают UI) — гасят типичную для зала соревнований
    # ситуацию "вайфай моргнул на секунду". Без них один неудачный PATCH
    # улетает в офлайн-очередь, а следующий апдейт в FIFO (например,
    # апдейт СЛЕДУЮЩЕГО матча той же категории) может тут же успешно
    # проехать и обогнать его на сервере — из-за этого на табло на сайте
    # какое-то время показывается не тот матч текущим (см. диагностику
    # гонки WB-финал/LB-раунд-1 при одновременной готовности обоих).
    _RETRY_DELAYS = (0.3, 0.8, 1.5)

    # ── внутренний хелпер: попытка + запись в очередь при неудаче ──
    def _try(self, operation: str, retry_payload: dict, fn):
        if not self.enabled:
            return None
        if self.force_queue:
            self.state.enqueue(operation, retry_payload)
            return None
        last_error: ApiClientError | None = None
        for attempt, delay in enumerate((0.0, *self._RETRY_DELAYS)):
            if delay:
                time.sleep(delay)
            try:
                return fn()
            except ApiClientError as e:
                last_error = e
                if attempt > 0:
                    print(f"[sync] {operation} -> повтор {attempt} не удался: {e}")
        # Все быстрые повторы (в сумме ~2.5с) исчерпаны — реальная, не
        # секундная просадка сети. Кладём в офлайн-очередь как раньше и
        # сразу же (в отдельном потоке, не блокируя этот FIFO-воркер и не
        # ломая порядок остальных задач в очереди) пробуем разгрести всю
        # офлайн-очередь, не дожидаясь периодического тика раз в 15с.
        self.state.enqueue(operation, retry_payload)
        print(f"[sync] {operation} -> в офлайн-очередь (нет связи?): {last_error}")
        self._trigger_immediate_flush()
        return None

    # ── гарантированное удаление на сервере ─────────────────────
    def _delete_on_server(self, entity_type, op, local_id, remote_id, payload):
        """Удалить запись на сервере и НИКОГДА не потерять операцию молча.

        Раньше удаление могло «молча потеряться» (спортсмен удалялся в
        десктопе, но оставался на сайте) через любой из путей:
          * неожиданное исключение в API-клиенте (не ApiClientError)
            пробрасывалось наверх и глоталось вызывающим кодом — в очередь
            ничего не попадало;
          * sync выключен / force_queue не проверялись;
          * 401/405/5xx/нет сети уводили операцию в очередь, откуда её потом
            МОЛЧА выбрасывал flush_pending после 50 неудачных попыток.
        Теперь: любая ошибка -> в офлайн-очередь; 404 = на сервере уже
        удалено (успех); успешное удаление снимает id_map. Операция из
        очереди больше никогда не выбрасывается (см. flush_pending) и
        доедет, как только проблема (токен/сеть) исчезнет.
        """
        if remote_id is None:
            # На сервере записи никогда не было — удалять нечего. Это НЕ
            # потеря данных: local_id никогда не синкался.
            print(f"[sync] {op}: remote_id отсутствует для local={local_id} — "
                  "на сервере записи не было, удалять нечего")
            return True
        if not self.enabled or self.force_queue:
            self.state.enqueue(op, payload)
            print(f"[sync] {op} -> в офлайн-очередь (sync выключен или force_queue)")
            return False
        delete_fn = getattr(self.api, op, None)
        if delete_fn is None:
            print(f"[sync] {op}: нет метода в api_client — запись останется на сайте; "
                  "кладём в очередь, чтобы не потерять")
            self.state.enqueue(op, payload)
            return False
        try:
            delete_fn(remote_id)
        except ApiClientError as e:
            if e.status_code == 404:
                self.state.map_delete(entity_type, local_id)
                print(f"[sync] {op}: 404 — на сервере уже удалено")
                return True
            self.state.enqueue(op, payload)
            print(f"[sync] {op} -> в офлайн-очередь: {e}")
            return False
        except Exception as e:
            self.state.enqueue(op, payload)
            print(f"[sync] {op} -> в офлайн-очередь (неожиданная ошибка): {e}")
            return False
        self.state.map_delete(entity_type, local_id)
        return True

    def _record_blocked(self, row):
        """Помечает операцию (delete/update/create), упёршуюся в потолок
        повторов, как «заблокированную» для показа пользователю. Из очереди
        её НЕ выбрасываем — она продолжит пытаться при каждом flush."""
        key = (row["operation"], row["payload"])
        with self._blocked_lock:
            for b in self.blocked_ops:
                if (b["operation"], b["payload"]) == key:
                    return
            self.blocked_ops.append({
                "operation": row["operation"],
                "payload": row["payload"],
                "attempts": row["attempts"],
                "last_error": row["last_error"],
            })
        print(f"[sync] ⚠ {row['operation']} id={row['id']} не долетает до сервера "
              f"({row['attempts']} попыток) — операция СОХРАНЕНА в очереди, "
              "предупреждаем пользователя")

    def take_blocked_warning(self):
        """Отдаёт и очищает список заблокированных операций — вызывается из
        UI-тикера, чтобы показать пользователю предупреждение (не блокирует
        очередь, не теряет операцию: она остаётся в pending_queue)."""
        with self._blocked_lock:
            if not self.blocked_ops:
                return None
            blocked, self.blocked_ops = self.blocked_ops, []
            return blocked

    def _trigger_immediate_flush(self):
        """Дёргает flush_pending() в фоновом потоке. Механизм coalescing:
        если поток уже запущен (даже если он ещё ждёт _flush_lock), новый
        поток не создаётся — один flush обработает все накопившиеся операции."""
        if getattr(self, "_flush_thread_running", False):
            return
        self._flush_thread_running = True
        def _run():
            try:
                self.flush_pending()
            finally:
                self._flush_thread_running = False
        threading.Thread(target=_run, daemon=True, name="sync-immediate-flush").start()

    # ── спортсмен: карточка из локальной таблицы athletes ───────
    def on_athlete_created(self, aid, first_name, last_name, birth_date,
                           gender, club, rank, photo_path, coach_name=None,
                           iin=None, phone=None):
        payload = {
            "aid": aid, "first_name": first_name, "last_name": last_name,
            "birth_date": birth_date, "gender": gender, "club": club,
            "rank": rank, "photo_path": photo_path, "coach_name": coach_name,
            "iin": iin, "phone": phone,
        }

        def go():
            remote = self.api.create_athlete(
                full_name=f"{first_name} {last_name}".strip(),
                club_name=club or None,
                birth_date=birth_date,
                gender=gender,
                rank=rank or None,
                photo_path=photo_path or None,
                coach_name=coach_name or None,
                iin=iin or None,
                phone=phone or None,
            )
            if not self.state.map_set("athlete", aid, remote["id"]):
                print(f"[sync] WARNING athlete {aid} ({first_name} {last_name}) "
                      f"NOT bound to remote {remote['id']}: that remote already "
                      "belongs to another local card — looks like a duplicate "
                      "athlete in the registry")
            return remote["id"]

        return self._try("create_athlete", payload, go)

    def on_athlete_updated(self, aid, first_name, last_name, birth_date,
                           gender, club, rank, photo_path, coach_name=None,
                           iin=None, phone=None, is_hidden=None):
        remote_athlete_id = self.state.map_get("athlete", aid)
        payload = {
            "aid": aid, "first_name": first_name, "last_name": last_name,
            "birth_date": birth_date, "gender": gender, "club": club,
            "rank": rank, "photo_path": photo_path, "coach_name": coach_name,
            "iin": iin, "phone": phone, "is_hidden": is_hidden,
        }
        if remote_athlete_id is None:
            self.state.enqueue("update_athlete", payload)
            return None

        def go():
            self.api.update_athlete(
                remote_athlete_id,
                full_name=f"{first_name} {last_name}".strip(),
                club_name=club or None,
                birth_date=birth_date,
                gender=gender,
                rank=rank or None,
                photo_path=photo_path or None,
                # "" тоже должно долететь до API (отвязка тренера) — только
                # None ("поле не менялось") тут не подходит под UNSET-логику
                # api_client.update_athlete, поэтому передаём coach_name как
                # есть, без "or None" (в отличие от club/rank/photo_path выше).
                coach_name=coach_name,
                iin=iin,
                phone=phone,
                is_hidden=is_hidden,
            )
            return remote_athlete_id

        return self._try("update_athlete", payload, go)

    # ── тренер: карточка из локальной таблицы coaches ────────────
    def on_coach_created(self, cid, full_name, club, photo_path, bio,
                          first_name=None, last_name=None, birth_date=None,
                          iin=None, qualification=None, city=None, phone=None):
        payload = {"cid": cid, "full_name": full_name, "club": club,
                   "photo_path": photo_path, "bio": bio,
                   "first_name": first_name, "last_name": last_name,
                   "birth_date": birth_date, "iin": iin,
                   "qualification": qualification, "city": city, "phone": phone}

        def go():
            remote = self.api.create_coach(
                full_name=full_name, club_name=club or None,
                photo_path=photo_path or None, bio=bio or None,
                first_name=first_name or None, last_name=last_name or None,
                birth_date=birth_date or None, iin=iin or None,
                qualification=qualification or None, city_name=city or None,
                phone=phone or None,
            )
            if not self.state.map_set("coach", cid, remote["id"]):
                print(f"[sync] WARNING coach {cid} ({full_name}) NOT bound to "
                      f"remote {remote['id']}: that remote already belongs to "
                      "another local card — looks like a duplicate")
            return remote["id"]

        return self._try("create_coach", payload, go)

    def on_coach_updated(self, cid, full_name, club, photo_path, bio,
                          first_name=None, last_name=None, birth_date=None,
                          iin=None, qualification=None, city=None, phone=None,
                          is_hidden=None):
        remote_coach_id = self.state.map_get("coach", cid)
        payload = {"cid": cid, "full_name": full_name, "club": club,
                   "photo_path": photo_path, "bio": bio,
                   "first_name": first_name, "last_name": last_name,
                   "birth_date": birth_date, "iin": iin,
                   "qualification": qualification, "city": city, "phone": phone,
                   "is_hidden": is_hidden}
        if remote_coach_id is None:
            self.state.enqueue("update_coach", payload)
            return None

        def go():
            self.api.update_coach(
                remote_coach_id, full_name=full_name, club_name=club or None,
                photo_path=photo_path or None, bio=bio or None,
                first_name=first_name or None, last_name=last_name or None,
                birth_date=birth_date or None, iin=iin or None,
                qualification=qualification or None, city_name=city or None,
                phone=phone or None, is_hidden=is_hidden,
            )
            return remote_coach_id

        return self._try("update_coach", payload, go)

    def on_coach_deleted(self, cid):
        # Та же схема, что on_athlete_deleted: гасим ещё не отправленные
        # create/update этого тренера в очереди, потом гарантированно
        # удаляем и на сервере, если он уже туда улетел.
        self.state.purge_pending("create_coach", "cid", cid)
        self.state.purge_pending("update_coach", "cid", cid)

        remote_id = self.state.map_get("coach", cid)
        self._delete_on_server("coach", "delete_coach", cid, remote_id,
                               {"cid": cid, "remote_id": remote_id})

    # ── клуб ───────────────────────────────────────────────────
    def on_club_created(self, cid, name, city=None, address=None, founded_date=None, logo_path=None, phone=None):
        payload = {"cid": cid, "name": name, "city": city, "address": address,
                   "founded_date": founded_date, "logo_path": logo_path, "phone": phone}

        # Если клуб уже синхронизирован (create ушёл ранее, но ответ
        # потерялся и операция повисла в очереди) — не создаём второй раз,
        # а просто проталкиваем pending-операции и возвращаем существующий id.
        already = self.state.map_get("club", cid)
        if already is not None:
            self.state.purge_pending("create_club", "cid", cid)
            return already

        def go():
            remote = self.api.create_club(
                name=name, city_name=city or None, address=address or None,
                founded_date=founded_date, logo_path=logo_path or None,
                phone=phone or None,
            )
            if not self.state.map_set("club", cid, remote["id"]):
                print(f"[sync] WARNING club {cid} ({name}) NOT bound to remote "
                      f"{remote['id']}: that remote already belongs to another "
                      "local card — looks like a duplicate")
            return remote["id"]

        return self._try("create_club", payload, go)

    def on_club_updated(self, cid, name=None, city=None, address=None, founded_date=None, logo_path=None, phone=None):
        remote_club_id = self.state.map_get("club", cid)
        payload = {"cid": cid, "name": name, "city": city, "address": address,
                   "founded_date": founded_date, "logo_path": logo_path, "phone": phone}
        if remote_club_id is None:
            self.state.enqueue("update_club", payload)
            return None

        def go():
            self.api.update_club(
                remote_club_id,
                name=name, city_name=city or None, address=address or None,
                founded_date=founded_date, logo_path=logo_path or None,
                phone=phone or None,
            )
            return remote_club_id

        return self._try("update_club", payload, go)

    def on_club_deleted(self, cid):
        self.state.purge_pending("create_club", "cid", cid)
        self.state.purge_pending("update_club", "cid", cid)

        remote_id = self.state.map_get("club", cid)
        self._delete_on_server("club", "delete_club", cid, remote_id,
                               {"cid": cid, "remote_id": remote_id})

    # ── спортсмен-участник: поиск или создание на сервере ───────
    # local_athlete_id — id из ЛОКАЛЬНОЙ таблицы athletes (реестр
    # "Спортсмены"), если участник турнира был привязан к карточке.
    # Если карточка уже засинкана (on_athlete_created отработал раньше) —
    # переиспользуем готовый remote id вместо поиска/создания по имени,
    # чтобы не плодить дубли на сайте.
    def _find_or_create_athlete(self, name: str, club: str | None,
                                 local_athlete_id: int | None = None) -> int | None:
        if local_athlete_id is not None:
            remote_id = self.state.map_get("athlete", local_athlete_id)
            if remote_id is not None:
                return remote_id
        # fallback: участник без привязки к карточке (старые записи / ручной ввод)
        try:
            matches = self.api.search_athletes(name, club)
        except ApiClientError:
            matches = []
        for m in matches:
            if m["full_name"].strip().lower() == name.strip().lower():
                return m["id"]
        try:
            created = self.api.create_athlete(full_name=name, club_name=club or None)
            return created["id"]
        except ApiClientError as e:
            print(f"[sync] не удалось создать/найти спортсмена '{name}': {e}")
            return None

    # ── турнир ───────────────────────────────────────────────────
    def _entity_exists_locally(self, table: str, id_col: str, eid: int) -> bool:
        """Проверяет, существует ли запись в локальной БД. Если сущность
        удалена локально — соответствующий update в очереди мёртвый."""
        try:
            conn = sqlite3.connect(str(_TOURNAMENT_DB_PATH))
            try:
                return conn.execute(
                    f"SELECT 1 FROM {table} WHERE {id_col}=?", (eid,)
                ).fetchone() is not None
            finally:
                conn.close()
        except Exception:
            return True

    def _match_exists_locally(self, mid: int) -> bool:
        return self._entity_exists_locally("matches", "id", mid)

    def _athlete_exists_locally(self, aid: int) -> bool:
        return self._entity_exists_locally("athletes", "id", aid)

    def _coach_exists_locally(self, cid: int) -> bool:
        return self._entity_exists_locally("coaches", "id", cid)

    def _club_exists_locally(self, cid: int) -> bool:
        return self._entity_exists_locally("clubs", "id", cid)

    def on_tournament_created(self, tid, name, date, location,
                               weight_tolerance=None, bracket_system=None, format_type=None):
        # Сохраняем снимок ДО попытки отправки — нужен, если позже
        # соревнование "протухнет" на сервере (например, база была
        # пересоздана) и его придётся пересоздавать автоматически.
        self.state.save_competition_source(
            tid, name, date, location, weight_tolerance, bracket_system, format_type
        )

        def go():
            remote = self.api.create_competition(
                name, date, location, weight_tolerance, bracket_system, format_type
            )
            self.state.map_set("competition", tid, remote["id"])
            return remote["id"]

        return self._try(
            "create_competition",
            {
                "tid": tid, "name": name, "date": date, "location": location,
                "weight_tolerance": weight_tolerance, "bracket_system": bracket_system,
                "format_type": format_type,
            },
            go,
        )

    def _backfill_competition_source_from_local_db(self, tid) -> None:
        """Для турниров, созданных ДО включения самолечения (нет снимка
        competition_source): читает name/date/location напрямую из
        armwrestling.db и сохраняет снимок — тот же приём, что раньше
        приходилось делать руками через fix_stale_competition.py."""
        if not _TOURNAMENT_DB_PATH.exists():
            return
        try:
            conn = sqlite3.connect(str(_TOURNAMENT_DB_PATH))
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT name, date, location, weight_tolerance, bracket_system, format_type "
                    "FROM tournaments WHERE id=?", (tid,)
                ).fetchone()
            finally:
                conn.close()
        except Exception as exc:
            print(f"[sync] _backfill tid={tid}: {exc}")
            return
        if row is None:
            return
        self.state.save_competition_source(
            tid, row["name"], row["date"], row["location"],
            row["weight_tolerance"], row["bracket_system"], row["format_type"],
        )
        print(f"[sync] снимок competition_source для tid={tid} восстановлен из armwrestling.db")

    def _recreate_competition(self, tid) -> int | None:
        """Пересоздаёт соревнование на сервере по сохранённому снимку и
        обновляет id_map. Возвращает None, если восстановить данные турнира
        не удалось вообще ниоткуда."""
        source = self.state.get_competition_source(tid)
        if source is None:
            # Снимка нет — вероятно, турнир создан до включения самолечения.
            # Раньше это чинилось вручную через fix_stale_competition.py,
            # теперь пробуем восстановить снимок сами прямо из локальной БД.
            self._backfill_competition_source_from_local_db(tid)
            source = self.state.get_competition_source(tid)
        if source is None:
            print(
                f"[sync] не могу пересоздать соревнование tid={tid}: нет ни снимка "
                "competition_source, ни записи в armwrestling.db (турнир, похоже, "
                "был удалён локально)"
            )
            return None
        remote = self.api.create_competition(
            source["name"], source["date"], source["location"],
            source["weight_tolerance"], source["bracket_system"], source["format_type"],
        )
        self.state.map_set("competition", tid, remote["id"])
        print(f"[sync] соревнование tid={tid} пересоздано на сервере, новый remote_id={remote['id']}")
        return remote["id"]

    def _is_stale_competition_error(self, e: ApiClientError) -> bool:
        return e.status_code == 404

    def _self_heal_missing_tournament(self, tid) -> None:
        """Вызывается, когда _recreate_competition окончательно не смог
        восстановить турнир (нет ни снимка competition_source, ни записи в
        armwrestling.db) — то есть турнир был удалён локально в обход
        on_tournament_deleted (например, через reset_db/пересоздание БД).
        Без этого зависшая операция по несуществующему tid раз за разом
        проваливается в flush_pending(), а flush_pending() останавливается
        на первой же неудаче (чтобы не нарушать порядок турнир->категория->
        участник) — и тем самым НАВСЕГДА блокирует отправку всех остальных,
        живых турниров. Здесь применяется та же зачистка очереди по tid,
        что и в on_tournament_deleted, чтобы разгрести затор."""
        removed = 0
        removed += self.state.purge_pending("create_competition", "tid", tid)
        removed += self.state.purge_pending("create_category", "tid", tid)
        removed += self.state.purge_pending("create_participant", "tid", tid)
        removed += self.state.purge_pending("create_match", "tournament_id", tid)
        removed += self.state.purge_pending("update_match", "tournament_id", tid)
        print(
            f"[sync] tid={tid} не восстановить (удалён локально) — "
            f"вычищено {removed} операций из очереди, чтобы не блокировать "
            "остальные турниры"
        )

    # ── категория ────────────────────────────────────────────────
    def on_category_created(self, tid, cid, name, max_weight, hand, age_category=None):
        remote_competition_id = self.state.map_get("competition", tid)
        if remote_competition_id is None:
            self.state.enqueue(
                "create_category",
                {"tid": tid, "cid": cid, "name": name, "max_weight": max_weight, "hand": hand},
            )
            return None

        def go():
            comp_id = remote_competition_id
            try:
                remote = self.api.create_category(comp_id, name, max_weight, hand)
            except ApiClientError as e:
                if not self._is_stale_competition_error(e):
                    raise
                comp_id = self._recreate_competition(tid)
                if comp_id is None:
                    self._self_heal_missing_tournament(tid)
                    return None
                remote = self.api.create_category(comp_id, name, max_weight, hand)
            self.state.map_set("category", cid, remote["id"])
            return remote["id"]

        return self._try(
            "create_category",
            {"tid": tid, "cid": cid, "name": name, "max_weight": max_weight, "hand": hand},
            go,
        )

    # ── участник ─────────────────────────────────────────────────
    # добавлен параметр athlete_id=None: id карточки из локальной таблицы
    # athletes, если участник был выбран из реестра (см. _add_participant_dialog).
    def on_participant_added(self, tid, pid, name, weight, club, category_id, hand,
                              age_category, athlete_id=None):
        remote_competition_id = self.state.map_get("competition", tid)
        remote_category_id = self.state.map_get("category", category_id)
        payload = {
            "tid": tid, "pid": pid, "name": name, "weight": weight, "club": club,
            "category_id": category_id, "hand": hand, "age_category": age_category,
            "athlete_id": athlete_id,
        }
        if remote_competition_id is None or remote_category_id is None:
            self.state.enqueue("create_participant", payload)
            return None

        def go():
            comp_id = remote_competition_id
            remote_athlete_id = self._find_or_create_athlete(name, club, local_athlete_id=athlete_id)
            if remote_athlete_id is None:
                raise ApiClientError("не удалось получить athlete_id")
            try:
                remote = self.api.create_participant(
                    comp_id, pid, remote_athlete_id, remote_category_id, weight, club
                )
            except ApiClientError as e:
                if not self._is_stale_competition_error(e):
                    raise
                comp_id = self._recreate_competition(tid)
                if comp_id is None:
                    self._self_heal_missing_tournament(tid)
                    return None
                remote = self.api.create_participant(
                    comp_id, pid, remote_athlete_id, remote_category_id, weight, club
                )
            self.state.map_set("participant", pid, remote["id"])
            self.state.map_set("athlete_of_participant", pid, remote_athlete_id)
            return remote["id"]

        return self._try("create_participant", payload, go)

    def on_participant_updated(self, tid, pid, name, weight, club, category_id, hand, age_category):
        """Обновление «снимка» участника после регистрации (перевзвешивание).
        Синхронизирует вес на сайт — он участвует в тай-брейке двоеборья."""
        remote_competition_id = self.state.map_get("competition", tid)
        remote_participant_id = self.state.map_get("participant", pid)
        if remote_competition_id is None or remote_participant_id is None:
            return None
        payload = {"tid": tid, "pid": pid, "weight": weight, "club": club}

        def go():
            self.api.update_participant(
                remote_competition_id, remote_participant_id,
                weight_at_event=weight, club_at_event=club)
            return remote_participant_id

        return self._try("update_participant", payload, go)
    
    def on_participant_deleted(self, pid, photo_url=None):
        # 0. отдельное фото участника в Cloudinary (загруженное под турнир)
        #    удаляем отдельно — десктоп сам это делать не может (нет API
        #    secret), поэтому шлём URL на бэкенд. Неудача уходит в
        #    офлайн-очередь (delete_photo) и повторится позже.
        if photo_url and "res.cloudinary.com" in photo_url:
            self._try("delete_photo", {"url": photo_url},
                      lambda: self.api.delete_photo(photo_url))

        # 1. если ещё не отправлен — вообще не даём ему уйти
        self.state.purge_pending("create_participant", "pid", pid)

        # 2. если уже был на сервере — удаляем и там, гарантированно
        remote_id = self.state.map_get("participant", pid)
        self._delete_on_server("participant", "delete_participant", pid, remote_id,
                               {"pid": pid, "remote_id": remote_id})

    def on_tournament_deleted(self, tid):
        # Турнир мог быть удалён до того, как он сам и/или его дети
        # (категории, участники, матчи) улетели на сервер. Если погасить
        # только create_competition, дочерние операции останутся в очереди
        # НАВСЕГДА — их remote_competition_id никогда не появится — и будут
        # блокировать flush_pending для ВСЕХ следующих турниров, т.к. очередь
        # идёт по порядку и останавливается на первой же неудаче.
        self.state.purge_pending("create_competition", "tid", tid)
        self.state.purge_pending("create_category", "tid", tid)
        self.state.purge_pending("create_participant", "tid", tid)
        self.state.purge_pending("create_match", "tournament_id", tid)
        self.state.purge_pending("update_match", "tournament_id", tid)

        remote_id = self.state.map_get("competition", tid)
        self._delete_on_server("competition", "delete_competition", tid, remote_id,
                               {"tid": tid, "remote_id": remote_id})

    def on_category_deleted(self, cid):
        # Та же логика, что и для турнира: если категория удалена до того,
        # как она сама и/или её дети (участники, матчи) улетели на сервер —
        # погасить нужно все дочерние операции, иначе они останутся в очереди
        # НАВСЕГДА (их remote_category_id никогда не появится) и заблокируют
        # flush_pending для всех последующих операций.
        self.state.purge_pending("create_category", "cid", cid)
        self.state.purge_pending("create_participant", "category_id", cid)
        self.state.purge_pending("create_match", "category_id", cid)
        self.state.purge_pending("update_match", "category_id", cid)

        remote_id = self.state.map_get("category", cid)
        self._delete_on_server("category", "delete_category", cid, remote_id,
                               {"cid": cid, "remote_id": remote_id})

    def on_athlete_deleted(self, aid):
        # 1. если карточка ещё не улетела на сервер — гасим её create/update
        #    прямо в очереди, чтобы не создать "призрака" после локального удаления
        self.state.purge_pending("create_athlete", "aid", aid)
        self.state.purge_pending("update_athlete", "aid", aid)

        # 2. если уже был на сервере — удаляем и там, гарантированно (любая
        #    ошибка уходит в офлайн-очередь, операция не теряется молча)
        remote_id = self.state.map_get("athlete", aid)
        self._delete_on_server("athlete", "delete_athlete", aid, remote_id,
                               {"aid": aid, "remote_id": remote_id})

    # ── матч ─────────────────────────────────────────────────────
    def on_match_created(self, mid, match: dict):
        remote_category_id = self.state.map_get("category", match["category_id"])
        remote_p1 = self.state.map_get("participant", match["p1_id"]) if match.get("p1_id") else None
        remote_p2 = self.state.map_get("participant", match["p2_id"]) if match.get("p2_id") else None
        remote_winner = (
            self.state.map_get("participant", match["winner_id"]) if match.get("winner_id") else None
        )
        payload = {"mid": mid, **match}

        if remote_category_id is None:
            self.state.enqueue("create_match", payload)
            return None

        def go():
            remote = self.api.create_match(
                category_id=remote_category_id,
                hand=match.get("hand", "Правая"),
                round_name=match.get("round_name"),
                bracket=match.get("bracket", "winners"),
                match_order=match.get("match_order", 0),
                stage=match.get("stage", 0),
                p1_id=remote_p1,
                p2_id=remote_p2,
                winner_id=remote_winner,
                p1_losses=match.get("p1_losses", 0),
                p2_losses=match.get("p2_losses", 0),
                is_bye=int(match.get("is_bye", 0)) > 0,
                status=match.get("status", "pending"),
                table_number=match.get("table_number"),
                mid=mid,
            )
            self.state.map_set("match", mid, remote["id"])
            return remote["id"]

        return self._try("create_match", payload, go)

    # ── reconcile: восстановление «потерянных» на сайте матчей ──
    def reconcile_missing_matches(self, tid, db_path=None):
        """Ищем локальные матчи турнира, отсутствующие на сайте (нет записи
        в id_map), и ставим для них create_match в офлайн-очередь.

        Зачем: матчи создаются на сервере ТОЛЬКО по событию локального
        изменения (on_match_created). Если сервер потерял/удалил матчи
        (сброс категории, ручная чистка, пересоздание БД сайта), а локально
        они остались и с тех пор не менялись — они на сайт сами не вернутся.
        Reconcile закрывает именно этот пробел: всё, что есть локально, но
        не замаплено, снова попадает в очередь и долетает (через _replay).

        Ограничения (чтобы не воскрешать чужой мусор):
          * только турнир tid (сироты других/удалённых турниров не трогаем);
          * только матчи, чья категория УЖЕ замаплена на сервер (иначе
            create_match навсегда повиснет в очереди как «ждёт category_id»);
          * матчи, где p1/p2/winner замаплены (или отсутствуют) — иначе
            сервер ответит 422 и операция застрянет в blocked.

        Возвращает число добавленных в очередь create_match."""
        import sqlite3 as _sqlite3
        db_path = db_path or _TOURNAMENT_DB_PATH
        added = 0
        try:
            db = _sqlite3.connect(str(db_path))
            db.row_factory = _sqlite3.Row
        except Exception as e:
            print(f"[sync] reconcile: не могу открыть локальную БД: {e}")
            return 0
        try:
            rows = db.execute(
                "SELECT * FROM matches WHERE tournament_id=?", (tid,)
            ).fetchall()
        except Exception as e:
            print(f"[sync] reconcile: ошибка чтения матчей: {e}")
            db.close()
            return 0
        db.close()

        for row in rows:
            mid = row["id"]
            if self.state.map_get("match", mid) is not None:
                continue
            if self.state.map_get("category", row["category_id"]) is None:
                continue
            missing_participants = [
                k for k in ("p1_id", "p2_id", "winner_id")
                if row[k] is not None and self.state.map_get("participant", row[k]) is None
            ]
            if missing_participants:
                print(f"[sync] reconcile mid={mid}: участники без id_map "
                      f"({missing_participants}) — пропускаю")
                continue
            payload = {"mid": mid, **dict(row)}
            self.state.enqueue("create_match", payload)
            added += 1
            print(f"[sync] reconcile mid={mid}: добавлен create_match "
                  f"(cat={row['category_id']}, hand={row['hand']})")
        return added

    # ── сброс/пересоздание сетки категории ──────────────────────
    def on_bracket_reset(self, category_id, hand, local_mids):
        """Database.clear_matches удаляет матчи из sqlite напрямую, без
        сети — иначе старые матчи (с их p1/p2) остаются висеть на сайте
        и дают дубли пар в живой очереди. Чистим id_map/офлайн-очередь
        для них и, если категория уже синкана, удаляем матчи на сервере.

        ВАЖНО: также чистим thread-очередь _sync_queue от устаревших
        update_match для этих mid — иначе фоновая нить подхватит старые
        операции и положит их в офлайн-очередь уже ПОСЛЕ того, как мы
        purge-нули create_match, и update_match повиснет навсегда
        с "ждёт create_match mid=..." """
        reset_mids = set(local_mids)

        # Помечаем mid как stale — _sync_worker_loop пропустит их,
        # когда достанет из очереди. Это безопаснее drain-режима:
        # drain мог пропустить элемент, добавленный конкурентно (гонка).
        self._bracket_reset_mids.update(reset_mids)

        for mid in reset_mids:
            self.state.map_delete("match", mid)
            self.state.purge_pending("create_match", "mid", mid)
            self.state.purge_pending("update_match", "mid", mid)

        remote_category_id = self.state.map_get("category", category_id)
        if remote_category_id is None:
            # Категория ещё не долетела до сервера — значит и матчей
            # там нет, чистить нечего.
            return None

        payload = {"category_id": remote_category_id, "hand": hand}

        def go():
            self.api.delete_matches_for_category(remote_category_id, hand)
            return True

        return self._try("delete_matches", payload, go)

    def on_match_updated(self, mid, match: dict):
        remote_match_id = self.state.map_get("match", mid)
        remote_p1 = self.state.map_get("participant", match["p1_id"]) if match.get("p1_id") else None
        remote_p2 = self.state.map_get("participant", match["p2_id"]) if match.get("p2_id") else None
        remote_winner = (
            self.state.map_get("participant", match["winner_id"]) if match.get("winner_id") else None
        )
        payload = {"mid": mid, **match}

        if remote_match_id is None:
            self.state.purge_pending("update_match", "mid", mid)
            self.state.enqueue("update_match", payload)
            return None

        # "table_number" здесь обычно вообще отсутствует в match (обычные
        # обновления счёта/победителя его не трогают) — если слепо взять
        # match.get("table_number"), отсутствующий ключ неотличим от явного
        # null, и update_match (после починки сентинелом) молча снял бы
        # трансляцию сетки с табло при каждом сканировании победителя.
        table_number_kwargs = (
            {"table_number": match["table_number"]} if "table_number" in match else {}
        )

        def go():
            try:
                self.api.update_match(
                    remote_match_id,
                    p1_id=remote_p1,
                    p2_id=remote_p2,
                    winner_id=remote_winner,
                    p1_losses=match.get("p1_losses"),
                    p2_losses=match.get("p2_losses"),
                    status=match.get("status"),
                    **table_number_kwargs,
                )
            except ApiClientError as e:
                if e.status_code == 404:
                    # Матч удалён на сервере (ребuild сетки) — снимаем mapping
                    # сразу, не ретрая и не засоряя офлайн-очередь: повторный
                    # PATCH к несуществующему матчу бессмысленен и лишь
                    # приводит к лишним повторам «404 не найден».
                    self.state.map_delete("match", mid)
                    print(f"[sync] update_match mid={mid}: 404 — матч удалён на сервере, пропускаем")
                    return remote_match_id
                raise
            return remote_match_id

        return self._try("update_match", payload, go)

    # ── стол: массовая простановка номера стола матчам категории ──
    # Вызывается из BracketWindow один раз при открытии окна сетки и
    # один раз после генерации сетки (см. armwrestling_tournament.py) —
    # НЕ на каждый скан/обновление панели, чтобы не плодить лишние
    # HTTP-запросы. Нужно для живого табло "кто с кем и за каким
    # столом" на сайте (см. /public/competitions/{id}/queue).
    def on_matches_table_assigned(self, mids, table_number):
        for mid in mids:
            remote_match_id = self.state.map_get("match", mid)
            payload = {"mid": mid, "table_number": table_number}
            if remote_match_id is None:
                self.state.purge_pending("update_match", "mid", mid)
                self.state.enqueue("update_match", payload)
                continue

            def go(remote_match_id=remote_match_id, table_number=table_number):
                try:
                    self.api.update_match(remote_match_id, table_number=table_number)
                except ApiClientError as e:
                    if e.status_code == 404:
                        self.state.map_delete("match", mid)
                        print(f"[sync] update_match mid={mid}: 404 — матч удалён на сервере, пропускаем")
                        return remote_match_id
                    raise
                return remote_match_id

            self._try("update_match", payload, go)

    # ── ручные места двоеборья ─────────────────────────────────
    # Полный снимок (замена) отправляется, когда жюри выбрало победителя
    # «спорной» группы в окне «Итоги двоеборья». overrides — список
    # {"category_id": remote, "participant_id": remote, "manual_rank": int}.
    def on_dvoeborie_overrides_changed(self, tid, overrides):
        remote_competition_id = self.state.map_get("competition", tid)
        if remote_competition_id is None:
            return None
        payload = {"tid": tid, "overrides": overrides}

        def go():
            self.api.sync_dvoeborie_overrides(remote_competition_id, overrides)
            return remote_competition_id

        return self._try("sync_dvoeborie_overrides", payload, go)

    # ── публикация ───────────────────────────────────────────────
    def publish_tournament(self, tid) -> tuple[bool, str]:
        remote_competition_id = self.state.map_get("competition", tid)
        if remote_competition_id is None:
            return False, (
                "Турнир ещё не синхронизирован с центральной базой "
                "(нет связи?). Нажмите «Повторить синхронизацию» и "
                "попробуйте снова."
            )
        try:
            self.api.publish_competition(remote_competition_id)
            return True, "Результаты опубликованы на сайте."
        except ApiClientError as e:
            return False, f"Не удалось опубликовать: {e}"

    def update_tournament_status(self, tid, status) -> tuple[bool, str]:
        """Обновляет фазу турнира: in_progress / completed."""
        remote_id = self.state.map_get("competition", tid)
        if remote_id is None:
            return False, "Турнир ещё не синхронизирован."
        try:
            self.api.update_competition_status(remote_id, status)
            return True, f"Статус обновлён → {status}"
        except ApiClientError as e:
            return False, f"Не удалось обновить статус: {e}"

    # ── повтор офлайн-очереди ───────────────────────────────────
    def flush_pending(self) -> tuple[int, int]:
        """Повторяет все операции из офлайн-очереди по порядку. Возвращает
        (успешно, осталось). Останавливается на первой операции, которая
        всё ещё не проходит (обычно значит: до сих пор нет сети) — чтобы не
        нарушать порядок зависимостей (турнир -> категория -> участник).

        Возвращаемые значения _replay:
          True  — операция выполнена, удаляем из очереди
          None  — ещё не готова (зависит от другой операции), пропускаем
          False — ошибка, стоп и повторим позже

        Многопроходный режим: операции, вернувшие None в первом проходе
        (например update_match, чей create_match ещё не обработан), будут
        повторены в следующих проходах — их зависимости уже разрешены.
        """
        MAX_RETRY_ATTEMPTS = 50
        if not self._flush_lock.acquire(blocking=False):
            print("[sync] flush_pending: уже выполняется в другом потоке — пропуск")
            return 0, self.state.pending_count()
        try:
            succeeded = 0
            # delete-операции, не долетевшие в ЭТОМ прогоне: пробуем их не
            # более одного раза за flush (иначе многопроходный цикл ниже
            # долбил бы сеть одним и тем же DELETE до 10 раз подряд).
            stalled: set[int] = set()
            for _ in range(10):
                made_progress = False
                for row in self.state.pending():
                    if not self.state.exists(row["id"]):
                        continue
                    if row["id"] in stalled:
                        continue
                    op = row["operation"]
                    is_delete = op.startswith("delete_")
                    if row["attempts"] >= MAX_RETRY_ATTEMPTS:
                        # НИКОГДА не выбрасываем операцию из очереди, даже
                        # create/update: 50 неудач подряд — это реальная
                        # проблема (неверный токен, нет роута, постоянные
                        # сбои сети), а не «битая» операция. Предупреждаем
                        # пользователя один раз и продолжаем пытаться при
                        # каждом flush — как только проблема исчезнет,
                        # операция доедет (иначе добавленные офлайн
                        # спортсмены/тренеры навсегда не попадут на сайт).
                        self._record_blocked(row)
                    payload = __import__("json").loads(row["payload"])
                    # Тихие логи: TRY/REPLAY FAIL/RESULT печатаем только при
                    # ПЕРВОЙ попытке операции (или при успехе), чтобы мёртвый
                    # сервер не спамил консоль одной и той же ошибкой каждые
                    # ~10с до бесконечности.
                    first_attempt = row["attempts"] == 0
                    if first_attempt:
                        print(f"[sync] TRY: {op} payload={payload}")
                    try:
                        ok = self._replay(op, payload, verbose=first_attempt)
                    except Exception as e:
                        # Одна упавшая операция не должна валить весь
                        # flush_pending (а значит и auto-sync тикер): любое
                        # неожиданное исключение считаем просто неудачей.
                        if first_attempt:
                            print(f"[sync] RESULT: {op} -> ОШИБКА {e}")
                        ok = False
                    if ok is True or first_attempt:
                        print(f"[sync] RESULT: {op} -> {ok}")

                    if ok is True:
                        self.state.mark_done(row["id"])
                        succeeded += 1
                        made_progress = True
                    elif ok is None:
                        continue
                    elif is_delete:
                        # Удаление не блокирует остальную очередь и не
                        # теряется молча: фиксируем ошибку, продолжаем слать
                        # следующие операции, а само удаление повторится при
                        # следующем flush_pending.
                        stalled.add(row["id"])
                        self.state.mark_failed(row["id"],
                                               row["last_error"] or "delete не долетел — повторим позже")
                    else:
                        self.state.mark_failed(row["id"], "flush_pending: unrecoverable error")
                        return succeeded, self.state.pending_count()
                if not made_progress:
                    break
            return succeeded, self.state.pending_count()
        finally:
            self._flush_lock.release()
            # Обновляем backoff по результату этого прогона: если ни одна
            # операция не доехала и очередь ещё не пуста — сервер, судя по
            # всему, недоступен, ждём _BACKOFF_SECONDS до следующей
            # периодической попытки. Прогресс есть — пробуем снова часто.
            now = time.time()
            if succeeded > 0 or self.state.pending_count() == 0:
                self._flush_backoff_until = 0.0
            else:
                self._flush_backoff_until = now + self._BACKOFF_SECONDS

    def _replay(self, operation: str, payload: dict, verbose: bool = False) -> bool:
        try:
            if operation == "delete_participant":
                delete_fn = getattr(self.api, "delete_participant", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["remote_id"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        return True
                    raise
                return True

            if operation == "delete_photo":
                delete_fn = getattr(self.api, "delete_photo", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["url"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        # Бэкенд ещё не обновлён (нет роута /sync/photos/delete) —
                        # не считаем ошибкой повтор роута; операция останется
                        # в очереди и доедет, когда роут появится.
                        return None
                    raise
                return True

            if operation == "delete_competition":
                delete_fn = getattr(self.api, "delete_competition", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["remote_id"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        return True
                    raise
                return True

            if operation == "delete_category":
                delete_fn = getattr(self.api, "delete_category", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["remote_id"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        return True
                    raise
                return True

            if operation == "delete_athlete":
                delete_fn = getattr(self.api, "delete_athlete", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["remote_id"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        return True
                    raise
                return True

            if operation == "delete_coach":
                delete_fn = getattr(self.api, "delete_coach", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["remote_id"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        return True
                    raise
                return True

            if operation == "delete_club":
                delete_fn = getattr(self.api, "delete_club", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["remote_id"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        return True
                    raise
                return True

            if operation == "create_club":
                remote = self.api.create_club(
                    name=payload["name"],
                    city_name=payload.get("city") or None,
                    address=payload.get("address") or None,
                    founded_date=payload.get("founded_date"),
                    logo_path=payload.get("logo_path") or None,
                    phone=payload.get("phone") or None,
                )
                self.state.map_set("club", payload["cid"], remote["id"])
                return True

            if operation == "update_club":
                remote_club_id = self.state.map_get("club", payload["cid"])
                if remote_club_id is None:
                    if not self._club_exists_locally(payload["cid"]):
                        print(f"[sync] update_club cid={payload['cid']}: клуб удалён локально — чистим очередь")
                        self.state.purge_pending("update_club", "cid", payload["cid"])
                        return True
                    print(f"[sync] DEBUG: update_club ждёт create_club cid={payload['cid']}")
                    return None
                try:
                    self.api.update_club(
                        remote_club_id,
                        name=payload.get("name"),
                        city_name=payload.get("city") or None,
                        address=payload.get("address") or None,
                        founded_date=payload.get("founded_date"),
                        logo_path=payload.get("logo_path") or None,
                        phone=payload.get("phone") or None,
                    )
                except ApiClientError as e:
                    if e.status_code == 404:
                        self.state.map_delete("club", payload["cid"])
                        print(f"[sync] update_club cid={payload['cid']}: 404 — клуб удалён на сервере")
                        return True
                    raise
                return True

            if operation == "delete_matches":
                delete_fn = getattr(self.api, "delete_matches_for_category", None)
                if delete_fn is None:
                    return False
                try:
                    delete_fn(payload["category_id"], payload["hand"])
                except ApiClientError as e:
                    if e.status_code == 404:
                        return True
                    raise
                return True

            if operation == "create_competition":
                remote = self.api.create_competition(
                    payload["name"], payload["date"], payload["location"],
                    payload.get("weight_tolerance"), payload.get("bracket_system"),
                    payload.get("format_type"),
                )
                self.state.map_set("competition", payload["tid"], remote["id"])
                return True

            if operation == "create_category":
                remote_competition_id = self.state.map_get("competition", payload["tid"])
                if remote_competition_id is None:
                    print(f"[sync] DEBUG: create_category ждёт competition tid={payload['tid']}")
                    return None
                try:
                    remote = self.api.create_category(
                        remote_competition_id, payload["name"], payload["max_weight"], payload["hand"]
                    )
                except ApiClientError as e:
                    if not self._is_stale_competition_error(e):
                        raise
                    remote_competition_id = self._recreate_competition(payload["tid"])
                    if remote_competition_id is None:
                        # Турнир безвозвратно потерян — самолечим очередь
                        # (в т.ч. и эту саму строку) и НЕ блокируем
                        # flush_pending для остальных турниров.
                        self._self_heal_missing_tournament(payload["tid"])
                        return True
                    remote = self.api.create_category(
                        remote_competition_id, payload["name"], payload["max_weight"], payload["hand"]
                    )
                self.state.map_set("category", payload["cid"], remote["id"])
                return True

            if operation == "create_athlete":
                remote = self.api.create_athlete(
                    full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
                    club_name=payload.get("club") or None,
                    birth_date=payload.get("birth_date"),
                    gender=payload.get("gender"),
                    rank=payload.get("rank") or None,
                    photo_path=payload.get("photo_path") or None,
                    coach_name=payload.get("coach_name") or None,
                    iin=payload.get("iin") or None,
                    phone=payload.get("phone") or None,
                )
                self.state.map_set("athlete", payload["aid"], remote["id"])
                return True

            if operation == "update_athlete":
                remote_athlete_id = self.state.map_get("athlete", payload["aid"])
                if remote_athlete_id is None:
                    if not self._athlete_exists_locally(payload["aid"]):
                        print(f"[sync] update_athlete aid={payload['aid']}: спортсмен удалён локально — чистим очередь")
                        self.state.purge_pending("update_athlete", "aid", payload["aid"])
                        return True
                    print(f"[sync] DEBUG: update_athlete ждёт create_athlete aid={payload['aid']}")
                    return None
                try:
                    self.api.update_athlete(
                        remote_athlete_id,
                        full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
                        club_name=payload.get("club") or None,
                        birth_date=payload.get("birth_date"),
                        gender=payload.get("gender"),
                        rank=payload.get("rank") or None,
                        photo_path=payload.get("photo_path") or None,
                        coach_name=payload.get("coach_name"),
                        iin=payload.get("iin"),
                        phone=payload.get("phone"),
                        is_hidden=payload.get("is_hidden"),
                    )
                except ApiClientError as e:
                    if e.status_code == 404:
                        self.state.map_delete("athlete", payload["aid"])
                        print(f"[sync] update_athlete aid={payload['aid']}: 404 — удалён на сервере")
                        return True
                    raise
                return True

            if operation == "create_coach":
                remote = self.api.create_coach(
                    full_name=payload["full_name"],
                    club_name=payload.get("club") or None,
                    photo_path=payload.get("photo_path") or None,
                    bio=payload.get("bio") or None,
                    first_name=payload.get("first_name") or None,
                    last_name=payload.get("last_name") or None,
                    birth_date=payload.get("birth_date") or None,
                    iin=payload.get("iin") or None,
                    qualification=payload.get("qualification") or None,
                    city_name=payload.get("city") or None,
                    phone=payload.get("phone") or None,
                )
                self.state.map_set("coach", payload["cid"], remote["id"])
                return True

            if operation == "update_coach":
                remote_coach_id = self.state.map_get("coach", payload["cid"])
                if remote_coach_id is None:
                    if not self._coach_exists_locally(payload["cid"]):
                        print(f"[sync] update_coach cid={payload['cid']}: тренер удалён локально — чистим очередь")
                        self.state.purge_pending("update_coach", "cid", payload["cid"])
                        return True
                    print(f"[sync] DEBUG: update_coach ждёт create_coach cid={payload['cid']}")
                    return None
                try:
                    self.api.update_coach(
                        remote_coach_id,
                        full_name=payload["full_name"],
                        club_name=payload.get("club") or None,
                        photo_path=payload.get("photo_path") or None,
                        bio=payload.get("bio") or None,
                        first_name=payload.get("first_name") or None,
                        last_name=payload.get("last_name") or None,
                        birth_date=payload.get("birth_date") or None,
                        iin=payload.get("iin") or None,
                        qualification=payload.get("qualification") or None,
                        city_name=payload.get("city") or None,
                        phone=payload.get("phone") or None,
                        is_hidden=payload.get("is_hidden"),
                    )
                except ApiClientError as e:
                    if e.status_code == 404:
                        self.state.map_delete("coach", payload["cid"])
                        print(f"[sync] update_coach cid={payload['cid']}: 404 — удалён на сервере")
                        return True
                    raise
                return True

            if operation == "create_participant":
                remote_competition_id = self.state.map_get("competition", payload["tid"])
                remote_category_id = self.state.map_get("category", payload["category_id"])
                if remote_competition_id is None or remote_category_id is None:
                    print(f"[sync] DEBUG: create_participant ждёт tid={payload['tid']}")
                    return None
                athlete_id = self.state.map_get("athlete_of_participant", payload["pid"])
                if athlete_id is None:
                    athlete_id = self._find_or_create_athlete(
                        payload["name"], payload["club"], local_athlete_id=payload.get("athlete_id")
                    )
                if athlete_id is None:
                    # Не удалось создать спортсмена на сервере (сеть/таймаут) —
                    # не блокируем всю очередь, вернёмся к нему в следующем проходе.
                    print(f"[sync] DEBUG: create_participant pid={payload['pid']} ждёт athlete")
                    return None
                try:
                    remote = self.api.create_participant(
                        remote_competition_id, payload["pid"], athlete_id,
                        remote_category_id, payload["weight"], payload["club"],
                    )
                except ApiClientError as e:
                    if not self._is_stale_competition_error(e):
                        raise
                    remote_competition_id = self._recreate_competition(payload["tid"])
                    if remote_competition_id is None:
                        # Турнир безвозвратно потерян — самолечим очередь
                        # (в т.ч. и эту саму строку) и НЕ блокируем
                        # flush_pending для остальных турниров.
                        self._self_heal_missing_tournament(payload["tid"])
                        return True
                    remote = self.api.create_participant(
                        remote_competition_id, payload["pid"], athlete_id,
                        remote_category_id, payload["weight"], payload["club"],
                    )
                self.state.map_set("participant", payload["pid"], remote["id"])
                return True

            if operation == "create_match":
                # Матч уже создан на сервере (id_map проставлен, например при
                # первом успешном create_match или когда тот же mid синкался
                # через другой путь) — повторный POST бессмысленен и может
                # упасть (например 422, если состав категории с тех пор
                # изменился), а упав, заблокировать всю FIFO-очередь позади.
                # Идемпотентно: операция выполнена, просто снимаем её.
                if self.state.map_get("match", payload["mid"]) is not None:
                    print(f"[sync] create_match mid={payload['mid']}: уже создан на сервере — пропускаю")
                    return True
                remote_category_id = self.state.map_get("category", payload["category_id"])
                if remote_category_id is None:
                    print(f"[sync] DEBUG: create_match ждёт category_id={payload['category_id']}")
                    return None
                remote_p1 = self.state.map_get("participant", payload["p1_id"]) if payload.get("p1_id") else None
                remote_p2 = self.state.map_get("participant", payload["p2_id"]) if payload.get("p2_id") else None
                remote_winner = (
                    self.state.map_get("participant", payload["winner_id"])
                    if payload.get("winner_id") else None
                )
                try:
                    remote = self.api.create_match(
                        category_id=remote_category_id, hand=payload.get("hand", "Правая"),
                        round_name=payload.get("round_name"), bracket=payload.get("bracket", "winners"),
                        match_order=payload.get("match_order", 0), stage=payload.get("stage", 0),
                        p1_id=remote_p1, p2_id=remote_p2, winner_id=remote_winner,
                        p1_losses=payload.get("p1_losses", 0), p2_losses=payload.get("p2_losses", 0),
                        is_bye=int(payload.get("is_bye", 0)) > 0, status=payload.get("status", "pending"),
                        table_number=payload.get("table_number"),
                        mid=payload.get("mid"),
                    )
                except ApiClientError as e:
                    if e.status_code == 404:
                        # Категория/соревнование удалены на сервере
                        self.state.map_delete("match", payload["mid"])
                        self.state.purge_pending("update_match", "mid", payload["mid"])
                        print(f"[sync] create_match mid={payload['mid']}: 404 — категория/соревнование удалены")
                        self.state.map_delete("category", payload["category_id"])
                        return True
                    raise
                self.state.map_set("match", payload["mid"], remote["id"])
                return True

            if operation == "update_match":
                remote_match_id = self.state.map_get("match", payload["mid"])
                if remote_match_id is None:
                    # Может матч был удалён локально (пересоздание сетки)?
                    if not self._match_exists_locally(payload["mid"]):
                        print(f"[sync] update_match mid={payload['mid']}: матч удалён локально — чистим очередь")
                        self.state.purge_pending("update_match", "mid", payload["mid"])
                        return True
                    # create_match ещё не прошёл — НЕ удаляем из очереди,
                    # чтобы table_number не потерялся. Вернём None: flush
                    # пропустит эту строку и вернётся к ней позже.
                    print(f"[sync] DEBUG: update_match ждёт create_match mid={payload['mid']}")
                    return None
                # ВАЖНО: p1_id/p2_id обязательно резолвим и шлём и здесь тоже.
                # Раньше их слали только из "быстрого" пути on_match_updated.go(),
                # а сюда, в _replay (когда update_match идёт через офлайн-очередь —
                # что происходит практически всегда при продвижении победителя в
                # следующий матч, т.к. на момент _place_player тот матч ещё не
                # создан на сервере), их не передавали вовсе. В итоге статус и
                # winner_id долетали, а САМА новая пара в следующем раунде на
                # сайте не появлялась — "победитель прошёл, а на сайте ничего
                # не меняется".
                remote_p1 = (
                    self.state.map_get("participant", payload["p1_id"])
                    if payload.get("p1_id") else None
                )
                remote_p2 = (
                    self.state.map_get("participant", payload["p2_id"])
                    if payload.get("p2_id") else None
                )
                remote_winner = (
                    self.state.map_get("participant", payload["winner_id"])
                    if payload.get("winner_id") else None
                )
                # "table_number" в payload присутствует ТОЛЬКО когда операция
                # родом из on_matches_table_assigned (назначение/снятие стола)
                # — обычные обновления счёта/победителя (on_match_updated)
                # этот ключ не кладут вовсе. Поэтому используем .get(...) с
                # проверкой "in", а не голый .get("table_number") — иначе
                # отсутствующий ключ и явный null (снятие трансляции)
                # выглядели бы одинаково и update_match не смог бы их отличить.
                table_number_kwargs = (
                    {"table_number": payload["table_number"]}
                    if "table_number" in payload else {}
                )
                try:
                    self.api.update_match(
                        remote_match_id, p1_id=remote_p1, p2_id=remote_p2, winner_id=remote_winner,
                        p1_losses=payload.get("p1_losses"), p2_losses=payload.get("p2_losses"),
                        status=payload.get("status"), **table_number_kwargs,
                    )
                except ApiClientError as e:
                    if e.status_code == 404:
                        # Матч удалён на сервере — чистим id_map и очередь
                        self.state.map_delete("match", payload["mid"])
                        print(f"[sync] update_match mid={payload['mid']}: 404 — матч удалён на сервере, пропускаем")
                        return True
                    raise
                return True

            if operation == "sync_dvoeborie_overrides":
                remote_competition_id = self.state.map_get("competition", payload["tid"])
                if remote_competition_id is None:
                    # create_competition ещё не прошёл — вернёмся позже.
                    return None
                self.api.sync_dvoeborie_overrides(
                    remote_competition_id, payload["overrides"])
                return True

            if operation == "update_participant":
                remote_competition_id = self.state.map_get("competition", payload["tid"])
                remote_participant_id = self.state.map_get("participant", payload["pid"])
                if remote_competition_id is None or remote_participant_id is None:
                    return None
                self.api.update_participant(
                    remote_competition_id, remote_participant_id,
                    weight_at_event=payload.get("weight"),
                    club_at_event=payload.get("club"))
                return True

        except ApiClientError as e:
            if verbose:
                print(f"[sync] REPLAY FAIL: {operation} -> {e}")

        return False


# Единый инстанс на процесс — импортируется как `from sync.sync_manager
# import sync_manager` и используется в обёртках над Database (см.
# armwrestling_tournament.py).
sync_manager = SyncManager()
