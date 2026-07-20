"""Тонкий клиент к /api/v1/sync/*. Каждый метод — один HTTP-запрос,
исключения (нет сети, таймаут, 5xx) пробрасываются наверх — вызывающий
код (sync_manager) решает, класть ли операцию в офлайн-очередь."""

import requests

from . import config


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
        try:
            resp = requests.request(
                method, url, json=json_body, params=params,
                headers=self._headers(), timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise ApiClientError(f"Сеть недоступна ({url}): {e}") from e

        if resp.status_code >= 400:
            raise ApiClientError(
                f"{method} {path} -> {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json() if resp.content else {}

    # ── спортсмены ────────────────────────────────────────────
    def search_athletes(self, name: str, club: str | None = None):
        params = {"q": name}
        if club:
            params["club"] = club
        return self._request("GET", "/athletes/search", params=params)

    def create_athlete(self, full_name, club_name=None, gender=None, birth_date=None,
                        rank=None, photo_path=None):
        return self._request("POST", "/athletes", json_body={
            "full_name": full_name, "club_name": club_name,
            "gender": gender, "birth_date": birth_date, "rank": rank,
            "photo_path": photo_path,
        })

    def update_athlete(self, remote_athlete_id, full_name=None, club_name=None,
                        gender=None, birth_date=None, rank=None, photo_path=None):
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
        return self._request("PATCH", f"/athletes/{remote_athlete_id}", json_body=body)

    # ── соревнования ─────────────────────────────────────────
    def create_competition(self, name, date, location_name=None):
        return self._request("POST", "/competitions", json_body={
            "name": name, "date": date, "location_name": location_name,
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

    def publish_competition(self, remote_competition_id):
        return self._request("POST", f"/competitions/{remote_competition_id}/publish")
    
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

    def update_match(self, remote_match_id, winner_id=None, p1_losses=None,
                      p2_losses=None, status=None, table_number=None):
        body = {}
        if winner_id is not None:
            body["winner_id"] = winner_id
        if p1_losses is not None:
            body["p1_losses"] = p1_losses
        if p2_losses is not None:
            body["p2_losses"] = p2_losses
        if status is not None:
            body["status"] = status
        if table_number is not None:
            body["table_number"] = table_number
        return self._request("PATCH", f"/matches/{remote_match_id}", json_body=body)

    def ping(self):
        return self._request("GET", "/ping")
