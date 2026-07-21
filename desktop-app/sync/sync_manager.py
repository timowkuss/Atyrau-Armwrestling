"""Оркестрирует синхронизацию действий организатора с центральной БД в
реальном времени (см. ARCHITECTURE.md §5). Вызывается из обёрток над
методами Database (см. правки в armwrestling_tournament.py) — сам НИКОГДА
не бросает исключения наружу настолько, чтобы сломать локальную работу:
любая сетевая ошибка уходит в офлайн-очередь и повторяется позже.
"""

import sqlite3
import threading
from pathlib import Path

from .api_client import ApiClientError, SyncApiClient
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
        # Настоящая блокировка на случай, если flush_pending() вызовут
        # из нескольких мест одновременно (фоновый поток после генерации
        # сетки, периодический авто-тик UI, кнопка "Синхронизация") —
        # без неё оба вызова читают одну и ту же офлайн-очередь и оба
        # успевают отправить create_match для одних и тех же матчей до
        # того, как первый пометит их выполненными, что даёт дубли на
        # сервере (см. flush_pending).
        self._flush_lock = threading.Lock()

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
        if now - self._last_flush_attempt < 15:
            return None
        self._last_flush_attempt = now
        # flush_pending() сам себя защищает через _flush_lock (см. ниже),
        # так что если генерация сетки уже гонит очередь в фоновом потоке,
        # этот вызов просто сразу вернёт None вместо дублирования отправки.
        return self.flush_pending()

    # ── внутренний хелпер: попытка + запись в очередь при неудаче ──
    def _try(self, operation: str, retry_payload: dict, fn):
        if not self.enabled:
            return None
        if self.force_queue:
            self.state.enqueue(operation, retry_payload)
            return None
        try:
            return fn()
        except ApiClientError as e:
            self.state.enqueue(operation, retry_payload)
            print(f"[sync] {operation} -> в офлайн-очередь (нет связи?): {e}")
            return None

    # ── спортсмен: карточка из локальной таблицы athletes ───────
    def on_athlete_created(self, aid, first_name, last_name, birth_date,
                           gender, club, rank, photo_path):
        payload = {
            "aid": aid, "first_name": first_name, "last_name": last_name,
            "birth_date": birth_date, "gender": gender, "club": club,
            "rank": rank, "photo_path": photo_path,
        }

        def go():
            remote = self.api.create_athlete(
                full_name=f"{first_name} {last_name}".strip(),
                club_name=club or None,
                birth_date=birth_date,
                gender=gender,
                rank=rank or None,
                photo_path=photo_path or None,
            )
            self.state.map_set("athlete", aid, remote["id"])
            return remote["id"]

        return self._try("create_athlete", payload, go)

    def on_athlete_updated(self, aid, first_name, last_name, birth_date,
                           gender, club, rank, photo_path):
        remote_athlete_id = self.state.map_get("athlete", aid)
        payload = {
            "aid": aid, "first_name": first_name, "last_name": last_name,
            "birth_date": birth_date, "gender": gender, "club": club,
            "rank": rank, "photo_path": photo_path,
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
            )
            return remote_athlete_id

        return self._try("update_athlete", payload, go)

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
        conn = sqlite3.connect(str(_TOURNAMENT_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT name, date, location, weight_tolerance, bracket_system, format_type "
                "FROM tournaments WHERE id=?", (tid,)
            ).fetchone()
        finally:
            conn.close()
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
        return e.status_code == 404 and "оревнован" in str(e)

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

    def on_participant_updated(self, pid, name, weight, club, category_id, hand, age_category):
        # Обновление профиля участника ПОСЛЕ регистрации (например, поправили
        # вес) намеренно не синхронизируется в этой версии — центральная
        # competition_participants хранит "снимок" на момент регистрации.
        # Полноценный PATCH можно добавить по необходимости; пока это
        # осознанное упрощение Этапа 6, не баг.
        pass
    
    def on_participant_deleted(self, pid):
        # 1. если ещё не отправлен — вообще не даём ему уйти
        self.state.purge_pending("create_participant", "pid", pid)

        # 2. если уже был на сервере — пробуем удалить и там
        remote_id = self.state.map_get("participant", pid)
        if remote_id is None:
            return  # не долетел раньше — и не долетит теперь

        delete_fn = getattr(self.api, "delete_participant", None)
        if delete_fn is None:
            print("[sync] delete_participant: в api_client нет метода удаления — "
                "запись останется на сайте, удали вручную или добавь метод в API")
            return
        try:
            delete_fn(remote_id)
        except ApiClientError as e:
            self.state.enqueue("delete_participant", {"pid": pid, "remote_id": remote_id})
            print(f"[sync] delete_participant -> в офлайн-очередь: {e}")

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
        if remote_id is None:
            return
        delete_fn = getattr(self.api, "delete_competition", None)
        if delete_fn is None:
            print("[sync] delete_competition: в api_client нет метода удаления")
            return
        try:
            delete_fn(remote_id)
        except ApiClientError as e:
            self.state.enqueue("delete_competition", {"tid": tid, "remote_id": remote_id})

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
        if remote_id is None:
            return
        delete_fn = getattr(self.api, "delete_category", None)
        if delete_fn is None:
            print("[sync] delete_category: в api_client нет метода удаления")
            return
        try:
            delete_fn(remote_id)
        except ApiClientError as e:
            self.state.enqueue("delete_category", {"cid": cid, "remote_id": remote_id})
    
    def on_athlete_deleted(self, aid):
        # 1. если карточка ещё не улетела на сервер — гасим её create/update
        #    прямо в очереди, чтобы не создать "призрака" после локального удаления
        self.state.purge_pending("create_athlete", "aid", aid)
        self.state.purge_pending("update_athlete", "aid", aid)

        # 2. если уже был на сервере — пробуем удалить и там
        remote_id = self.state.map_get("athlete", aid)
        if remote_id is None:
            return  # не долетел раньше — и не долетит теперь

        delete_fn = getattr(self.api, "delete_athlete", None)
        if delete_fn is None:
            print("[sync] delete_athlete: в api_client нет метода удаления — "
                "запись останется на сайте, удали вручную или добавь метод в API")
            return
        try:
            delete_fn(remote_id)
        except ApiClientError as e:
            self.state.enqueue("delete_athlete", {"aid": aid, "remote_id": remote_id})
            print(f"[sync] delete_athlete -> в офлайн-очередь: {e}")

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
                is_bye=bool(match.get("is_bye", 0)),
                status=match.get("status", "pending"),
                table_number=match.get("table_number"),
            )
            self.state.map_set("match", mid, remote["id"])
            return remote["id"]

        return self._try("create_match", payload, go)

    # ── сброс/пересоздание сетки категории ──────────────────────
    def on_bracket_reset(self, category_id, hand, local_mids):
        """Database.clear_matches удаляет матчи из sqlite напрямую, без
        сети — иначе старые матчи (с их p1/p2) остаются висеть на сайте
        и дают дубли пар в живой очереди. Чистим id_map/офлайн-очередь
        для них и, если категория уже синкана, удаляем матчи на сервере."""
        for mid in local_mids:
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
                self.state.enqueue("update_match", payload)
                continue

            def go(remote_match_id=remote_match_id, table_number=table_number):
                self.api.update_match(remote_match_id, table_number=table_number)
                return remote_match_id

            self._try("update_match", payload, go)

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
        """
        # Не блокируем поток — если другой flush уже идёт (например, фоновый
        # поток после генерации сетки), просто выходим без работы: тот,
        # другой вызов доберёт всю текущую очередь сам. Без этой проверки
        # два одновременных flush_pending() читают одну и ту же очередь и
        # оба успевают выполнить create_match для одних и тех же матчей до
        # mark_done() — отсюда дубли матчей на сервере.
        if not self._flush_lock.acquire(blocking=False):
            print("[sync] flush_pending: уже выполняется в другом потоке — пропуск")
            return 0, self.state.pending_count()
        try:
            succeeded = 0
            for row in self.state.pending():
                if not self.state.exists(row["id"]):
                    continue
                op, payload = row["operation"], __import__("json").loads(row["payload"])
                print(f"[sync] TRY: {op} payload={payload}")
                ok = self._replay(op, payload)
                print(f"[sync] RESULT: {op} -> {ok}")

                if ok is True:
                    self.state.mark_done(row["id"])
                    succeeded += 1
                elif ok is None:
                    # Ещё не готово (create_match не прошёл) — пропускаем,
                    # оставляем в очереди, НЕ останавливаем flush.
                    continue
                else:
                    break
            return succeeded, self.state.pending_count()
        finally:
            self._flush_lock.release()

    def _replay(self, operation: str, payload: dict) -> bool:
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
                )
                self.state.map_set("athlete", payload["aid"], remote["id"])
                return True

            if operation == "update_athlete":
                remote_athlete_id = self.state.map_get("athlete", payload["aid"])
                if remote_athlete_id is None:
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
                    )
                except ApiClientError as e:
                    if e.status_code == 404:
                        self.state.map_delete("athlete", payload["aid"])
                        print(f"[sync] update_athlete aid={payload['aid']}: 404 — удалён на сервере")
                        return True
                    raise
                return True

            if operation == "create_participant":
                remote_competition_id = self.state.map_get("competition", payload["tid"])
                remote_category_id = self.state.map_get("category", payload["category_id"])
                if remote_competition_id is None or remote_category_id is None:
                    print(f"[sync] DEBUG: create_participant ждёт tid={payload['tid']}")
                    return None
                athlete_id = self._find_or_create_athlete(
                    payload["name"], payload["club"], local_athlete_id=payload.get("athlete_id")
                )
                if athlete_id is None:
                    return False
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
                        is_bye=bool(payload.get("is_bye", 0)), status=payload.get("status", "pending"),
                        table_number=payload.get("table_number"),
                    )
                except ApiClientError as e:
                    if e.status_code == 404:
                        # Категория/соревнование удалены на сервере —
                        # гасим create_match и связанный update_match
                        self.state.map_delete("match", payload["mid"])
                        self.state.purge_pending("update_match", "mid", payload["mid"])
                        print(f"[sync] create_match mid={payload['mid']}: 404 — категория удалена на сервере")
                        return True
                    raise
                self.state.map_set("match", payload["mid"], remote["id"])
                return True

            if operation == "update_match":
                remote_match_id = self.state.map_get("match", payload["mid"])
                if remote_match_id is None:
                    # create_match ещё не прошёл — НЕ удаляем из очереди,
                    # чтобы table_number не потерялся. Вернём None: flush
                    # пропустит эту строку и вернётся к ней позже.
                    print(f"[sync] DEBUG: update_match ждёт create_match mid={payload['mid']}")
                    return None
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
                remote_p1 = self.state.map_get("participant", payload["p1_id"]) if payload.get("p1_id") else None
                remote_p2 = self.state.map_get("participant", payload["p2_id"]) if payload.get("p2_id") else None
                try:
                    self.api.update_match(
                        remote_match_id,
                        p1_id=remote_p1, p2_id=remote_p2,
                        winner_id=remote_winner,
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

        except ApiClientError as e:
            print(f"[sync] REPLAY FAIL: {operation} -> {e}")

        return False


# Единый инстанс на процесс — импортируется как `from sync.sync_manager
# import sync_manager` и используется в обёртках над Database (см.
# armwrestling_tournament.py).
sync_manager = SyncManager()
