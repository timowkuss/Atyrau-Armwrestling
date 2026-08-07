"""Тонкий клиент к /api/v1/sync/*. Каждый метод — один HTTP-запрос,
исключения (нет сети, таймаут, 5xx) пробрасываются наверх — вызывающий
код (sync_manager) решает, класть ли операцию в офлайн-очередь.

Устойчивость к сбоям DNS/сети: GET-запросы (чтение изменений с сервера)
ретраятся с бэкоффом — кратковременный сбой резолва имени (как у
up.railway.app) поглощается ретраями, а не валит цикл поллера.
POST/PATCH/DELETE ретраями НЕ покрываются: повтор неидемпотентного
запроса мог бы создать дубль записи — их судьбой по-прежнему занимается
офлайн-очередь sync_manager."""

import time

import requests

from . import config

# Сбои соединения/DNS — до 3 повторов с бэкоффом 1/2/4 сек (~7 сек). За
# это время типичный «провал» DNS Railway успевает пройти сам.
_CONNECT_RETRIES = 3
_CONNECT_BACKOFF = 1.0

# Сентинел для PATCH-полей: отличает "поле не передано, не трогать"
# от "поле явно передано как null" (например, снять table_number,
# чтобы прекратить трансляцию сетки на табло сайта). default=None для
# этого не подходит — тогда "снять номер стола" и "не менять номер
# стола" выглядели бы одинаково, и снять номер стало бы невозможно.
UNSET = object()


class ApiClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SyncApiClient:
    def __init__(self, base_url=None, token=None, timeout=None):
        self.base_url = (base_url or config.API_BASE_URL).rstrip("/")
        self.token = token or config.DESKTOP_SYNC_TOKEN
        self.timeout = timeout or config.REQUEST_TIMEOUT_SECONDS

    def _headers(self):
        return {"X-Sync-Token": self.token, "Content-Type": "application/json"}

    def _request(self, method: str, path: str, json_body: dict | None = None, params=None):
        url = f"{self.base_url}{path}"
        attempts = _CONNECT_RETRIES + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                resp = requests.request(
                    method, url, json=json_body, params=params,
                    headers=self._headers(), timeout=self.timeout,
                )
            except requests.RequestException as e:
                if attempt < attempts - 1:
                    time.sleep(_CONNECT_BACKOFF * (2 ** attempt))
                    continue
                raise ApiClientError(f"Сеть недоступна ({url}): {e}") from e

            if resp.status_code >= 400:
                raise ApiClientError(
                    f"{method} {path} -> {resp.status_code}: {resp.text}",
                    status_code=resp.status_code,
                )
            return resp.json() if resp.content else {}
        raise ApiClientError(f"Сеть недоступна ({url})")

    # ── спортсмены ────────────────────────────────────────────
    # ── обратная синхронизация: что поменялось в админке сайта ─
    def get_athlete_changes(self, since: str | None = None):
        params = {"since": since} if since else None
        return self._request("GET", "/athletes/changes", params=params)

    def search_athletes(self, name: str, club: str | None = None):
        params = {"q": name}
        if club:
            params["club"] = club
        return self._request("GET", "/athletes/search", params=params)

    def create_athlete(self, full_name, club_name=None, gender=None, birth_date=None,
                        rank=None, photo_path=None, coach_name=None, iin=None, phone=None):
        return self._request("POST", "/athletes", json_body={
            "full_name": full_name, "club_name": club_name,
            "gender": gender, "birth_date": birth_date, "rank": rank,
            "photo_path": photo_path, "coach_name": coach_name,
            "iin": iin, "phone": phone,
        })

    def update_athlete(self, remote_athlete_id, full_name=None, club_name=None,
                        gender=None, birth_date=None, rank=None, photo_path=None,
                        coach_name=UNSET, iin=UNSET, phone=UNSET, is_hidden=UNSET):
        body = {}
        if full_name is not None:
            body["full_name"] = full_name
        if club_name is not None:
            body["club_name"] = club_name
        if gender is not None:
            body["gender"] = gender
        if birth_date is not None:
            body["birth_date"] = birth_date
        if rank is not None:
            body["rank"] = rank
        if photo_path is not None:
            body["photo_path"] = photo_path
        if coach_name is not UNSET:
            # "" — явная отвязка тренера, отличается от "не передано вовсе"
            # (та же логика сентинела, что у table_number в update_match).
            body["coach_name"] = coach_name
        if iin is not UNSET:
            body["iin"] = iin
        if phone is not UNSET:
            body["phone"] = phone
        if is_hidden is not UNSET:
            body["is_hidden"] = bool(is_hidden)
        return self._request("PATCH", f"/athletes/{remote_athlete_id}", json_body=body)

    # ── тренеры ──────────────────────────────────────────────
    def search_coaches(self, name: str):
        return self._request("GET", "/coaches/search", params={"q": name})

    def get_coach_changes(self, since: str | None = None):
        params = {"since": since} if since else None
        return self._request("GET", "/coaches/changes", params=params)

    def create_coach(self, full_name, club_name=None, photo_path=None, bio=None,
                      first_name=None, last_name=None, birth_date=None, iin=None,
                      qualification=None, city_name=None, phone=None):
        return self._request("POST", "/coaches", json_body={
            "full_name": full_name, "club_name": club_name,
            "photo_path": photo_path, "bio": bio,
            "first_name": first_name, "last_name": last_name,
            "birth_date": birth_date, "iin": iin,
            "qualification": qualification, "city_name": city_name,
            "phone": phone,
        })
    def update_coach(self, remote_coach_id, full_name=None, club_name=None,
                      photo_path=None, bio=None, first_name=None, last_name=None,
                      birth_date=None, iin=None, qualification=None, city_name=None,
                      phone=None, is_hidden=None):
        body = {}
        if full_name is not None:
            body["full_name"] = full_name
        if club_name is not None:
            body["club_name"] = club_name
        if photo_path is not None:
            body["photo_path"] = photo_path
        if bio is not None:
            body["bio"] = bio
        if first_name is not None:
            body["first_name"] = first_name
        if last_name is not None:
            body["last_name"] = last_name
        if birth_date is not None:
            body["birth_date"] = birth_date
        if iin is not None:
            body["iin"] = iin
        if qualification is not None:
            body["qualification"] = qualification
        if city_name is not None:
            body["city_name"] = city_name
        if phone is not None:
            body["phone"] = phone
        if is_hidden is not None:
            body["is_hidden"] = bool(is_hidden)
        return self._request("PATCH", f"/coaches/{remote_coach_id}", json_body=body)
    def delete_coach(self, remote_id):
        return self._request("DELETE", f"/coaches/{remote_id}")

    # ── клубы ────────────────────────────────────────────────
    def get_clubs(self):
        return self._request("GET", "/clubs")

    def create_club(self, name, city_name=None, address=None, founded_date=None, logo_path=None, phone=None):
        return self._request("POST", "/clubs", json_body={
            "name": name, "city_name": city_name, "address": address,
            "founded_date": founded_date, "logo_path": logo_path, "phone": phone,
        })

    def update_club(self, remote_club_id, name=None, city_name=None,
                    address=None, founded_date=None, logo_path=None, phone=None):
        body = {}
        if name is not None:
            body["name"] = name
        if city_name is not None:
            body["city_name"] = city_name
        if address is not None:
            body["address"] = address
        if founded_date is not None:
            body["founded_date"] = founded_date
        if logo_path is not None:
            body["logo_path"] = logo_path
        if phone is not None:
            body["phone"] = phone
        return self._request("PATCH", f"/clubs/{remote_club_id}", json_body=body)

    def delete_club(self, remote_id):
        return self._request("DELETE", f"/clubs/{remote_id}")

    def get_coach_rankings(self):
        """Рейтинг 'лучший тренер года' — читает ПУБЛИЧНЫЙ (не /sync)
        эндпоинт: это открытые данные сайта, X-Sync-Token не нужен.
        base_url настроен на .../api/v1/sync — подменяем последний
        сегмент на /public, отдельный конфиг ради одного GET заводить
        не стали."""
        public_base = self.base_url.rsplit("/sync", 1)[0] + "/public"
        resp = requests.get(f"{public_base}/coaches/rankings", timeout=self.timeout)
        if resp.status_code >= 400:
            raise ApiClientError(
                f"GET /coaches/rankings -> {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()

    # ── соревнования ─────────────────────────────────────────
    def create_competition(self, name, date, location_name=None,
                            weight_tolerance=None, bracket_system=None, format_type=None):
        return self._request("POST", "/competitions", json_body={
            "name": name, "date": date, "location_name": location_name,
            "weight_tolerance": weight_tolerance,
            "bracket_system": bracket_system,
            "format_type": format_type,
        })

    def create_category(self, remote_competition_id, name, max_weight=None, hand="Обе"):
        return self._request(
            "POST", f"/competitions/{remote_competition_id}/categories",
            json_body={"name": name, "max_weight": max_weight, "hand": hand},
        )

    def create_participant(self, remote_competition_id, local_participant_id, athlete_id,
                            category_id, weight_at_event=None, club_at_event=None):
        return self._request(
            "POST", f"/competitions/{remote_competition_id}/participants",
            json_body={
                "local_participant_id": local_participant_id,
                "athlete_id": athlete_id, "category_id": category_id,
                "weight_at_event": weight_at_event, "club_at_event": club_at_event,
            },
        )
    
    # ── удаление ─────────────────────────────────────────────
    def delete_athlete(self, remote_id):
        return self._request("DELETE", f"/athletes/{remote_id}")

    def delete_participant(self, remote_id):
        return self._request("DELETE", f"/participants/{remote_id}")

    def update_participant(self, remote_competition_id, remote_participant_id,
                           weight_at_event=None, club_at_event=None):
        """PATCH «снимка» участника — в первую очередь вес после контрольного
        взвешивания (тай-брейк двоеборья)."""
        return self._request(
            "PATCH", f"/competitions/{remote_competition_id}/participants/{remote_participant_id}",
            json_body={"weight_at_event": weight_at_event, "club_at_event": club_at_event},
        )

    def delete_photo(self, url):
        """Удаляет файл Cloudinary по его URL (десктоп сам это делать не
        может — нет API secret; бэкенд вызывает delete_cloudinary_photo)."""
        return self._request("POST", "/photos/delete", json_body={"url": url})

    def publish_competition(self, remote_competition_id):
        return self._request("POST", f"/competitions/{remote_competition_id}/publish")

    def sync_dvoeborie_overrides(self, remote_competition_id, overrides):
        """Отправляет полный снимок ручных мест двоеборья турнира:
        overrides = [{"category_id": ..., "participant_id": ..., "manual_rank": ...}]."""
        return self._request(
            "POST", f"/competitions/{remote_competition_id}/dvoeborie-overrides",
            json_body={"overrides": overrides},
        )

    def update_competition_status(self, remote_competition_id, status):
        return self._request("PATCH", f"/competitions/{remote_competition_id}/status",
                             json_body={"status": status})
    
    def delete_competition(self, remote_id):
        return self._request("DELETE", f"/competitions/{remote_id}")

    def delete_category(self, remote_id):
        return self._request("DELETE", f"/categories/{remote_id}")

    # ── матчи ────────────────────────────────────────────────
    def create_match(self, category_id, hand="Правая", round_name=None, bracket="winners",
                      match_order=0, stage=0, p1_id=None, p2_id=None, winner_id=None,
                      p1_losses=0, p2_losses=0, is_bye=False, status="pending",
                      table_number=None):
        return self._request("POST", "/matches", json_body={
            "category_id": category_id, "hand": hand, "round_name": round_name,
            "bracket": bracket, "match_order": match_order, "stage": stage,
            "p1_id": p1_id, "p2_id": p2_id, "winner_id": winner_id,
            "p1_losses": p1_losses, "p2_losses": p2_losses,
            "is_bye": is_bye, "status": status, "table_number": table_number,
        })

    def update_match(self, remote_match_id, p1_id=None, p2_id=None, winner_id=None,
                      p1_losses=None, p2_losses=None, status=None, table_number=UNSET):
        body = {}
        if p1_id is not None:
            body["p1_id"] = p1_id
        if p2_id is not None:
            body["p2_id"] = p2_id
        if winner_id is not None:
            body["winner_id"] = winner_id
        if p1_losses is not None:
            body["p1_losses"] = p1_losses
        if p2_losses is not None:
            body["p2_losses"] = p2_losses
        if status is not None:
            body["status"] = status
        if table_number is not UNSET:
            # table_number может быть None — это осознанный сброс (снять
            # категорию/руку с трансляции на табло), а не "поле не менялось".
            body["table_number"] = table_number
        return self._request("PATCH", f"/matches/{remote_match_id}", json_body=body)

    def delete_matches_for_category(self, remote_category_id, hand):
        return self._request(
            "DELETE", "/matches",
            params={"category_id": remote_category_id, "hand": hand},
        )

    def ping(self):
        return self._request("GET", "/ping")
