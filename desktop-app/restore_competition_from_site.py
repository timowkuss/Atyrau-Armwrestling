"""Восстановление турнира с сайта на десктоп.

Одно-короткий инструмент (аналог check_backend.py): тянет завершённый
турнир с публичного API сайта и воссоздаёт его в локальной БД десктопа —
турнир, категории, участников и всю сетку с результатами (реплеем
победителей через настоящий движок SingleEliminationEngine).

Запуск (из desktop-app):
    python restore_competition_from_site.py [remote_competition_id]

Если id не указан — берётся первый из списка /public/competitions.

Идемпотентность:
- уже существующий турнир с тем же названием не создаётся повторно;
- режим "repair" (запуск для существующего турнира) дозаписывает
  отсутствующие результаты: сопоставляет сыграные матчи с сайтом по
  составу (имена p1/p2), а не по stage/match_order — сетка на сайте
  могла быть перегенерирована и хранит мусорные дубликаты матчей.
"""

import re
import sys
from pathlib import Path

import requests

import armwrestling_tournament as app
from sync import pull_sync

API = "https://atyrau-armwrestling-production.up.railway.app"


def _parse_weight(cat_name: str):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kg", cat_name, re.IGNORECASE)
    return float(m.group(1).replace(",", ".")) if m else 0.0


def _dd_mm_yyyy(iso_date: str) -> str:
    parts = iso_date.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return iso_date


def _fetch_competition(remote_id):
    r = requests.get(f"{API}/api/v1/public/competitions", timeout=20)
    r.raise_for_status()
    items = r.json()["items"]
    if not items:
        raise SystemExit("[restore] на сайте нет турниров")
    comp = next((c for c in items if c["id"] == remote_id), items[0]) \
        if remote_id else items[0]
    meta = requests.get(
        f"{API}/api/v1/public/competitions/{comp['id']}", timeout=20).json()
    bracket = requests.get(
        f"{API}/api/v1/public/competitions/{comp['id']}/bracket",
        timeout=20).json()
    return comp, meta, bracket


def _names_of(rows):
    names = []
    for m in rows:
        for side in ("p1_name", "p2_name"):
            n = m.get(side)
            if n and n not in names:
                names.append(n)
    return names


def _replay_missing_results(db, engine, cid, hand, names,
                            site_rows, pid_by_name):
    """Дозапись результатов: любой локальный pending-матч, у которого на
    сайте нашёлся сыгранный аналог по составу, провести до конца.
    Возвращает число дозаписанных результатов и расхождений."""
    replayed, mismatches = 0, 0
    local = db.get_matches(cid, hand)
    by_names = {}
    for m in local:
        if m["status"] == "pending" and m["p1_id"] and m["p2_id"]:
            n1 = next((n for n, pid in pid_by_name.items()
                       if pid == m["p1_id"]), None)
            n2 = next((n for n, pid in pid_by_name.items()
                       if pid == m["p2_id"]), None)
            if n1 and n2:
                by_names[frozenset((n1, n2))] = m

    for sm in site_rows:
        winner_name = sm.get("winner_name")
        if not winner_name:
            continue
        pair = frozenset((sm.get("p1_name"), sm.get("p2_name")))
        lm = by_names.get(pair)
        if lm is None:
            continue  # матча такого состава локально нет (мусор с сайта)
        winner_pid = pid_by_name.get(winner_name)
        if winner_pid is None or winner_pid not in (lm["p1_id"], lm["p2_id"]):
            print(f"  [restore] ! победитель «{winner_name}» не в матче "
                  f"({pair.pop() if pair else '?'})")
            mismatches += 1
            continue
        engine.advance_winner(lm["id"], winner_pid)
        replayed += 1
    return replayed, mismatches


def main() -> int:
    remote_id = int(sys.argv[1]) if len(sys.argv) > 1 else None

    # Наполняем реестр спортсменов/тренеров/клубов (configure обязателен:
    # без него поллер пишет в файл "None" вместо БД).
    pull_sync.configure(db_path=str(app.DB_PATH))
    try:
        pull_sync.pull_sync_manager.poll_once()
        print("[restore] реестр спортсменов/тренеров/клубов синхронизирован")
    except Exception as e:  # noqa: BLE001
        print(f"[restore] реестр не подтянулся ({e}) — продолжаю без связей")

    comp, meta, bracket = _fetch_competition(remote_id)
    name = comp["name"].strip()
    db = app.Database()

    athlete_by_name = {}
    for a in db.conn.execute(
            "SELECT id, first_name, last_name FROM athletes").fetchall():
        full = f"{a['first_name']} {a['last_name']}".strip()
        if full:
            athlete_by_name[full] = a["id"]

    existing = db.conn.execute(
        "SELECT id FROM tournaments WHERE name=?", (name,)).fetchone()
    if not existing:
        tid = db.create_tournament(
            name, _dd_mm_yyyy(comp["date"]),
            comp.get("location_city_name") or "",
            weight_tolerance=meta.get("weight_tolerance") or 0,
            bracket_system=meta.get("bracket_system") or "single",
            format_type=meta.get("format_type") or "separate")
        print(f"[restore] турнир #{tid}: «{name}» от {comp['date']}")
    else:
        tid = existing["id"]
        print(f"[restore] турнир #{tid} уже есть — режим починки "
              "(дозапись пропущенных результатов)")

    hands = sorted({m["hand"] for m in bracket})
    total_mismatches = 0

    for cat_meta in meta["categories"]:
        cat_name = cat_meta["name"]
        cat_rows = [m for m in bracket if m["category_name"] == cat_name]
        if not cat_rows:
            continue
        row = db.conn.execute(
            "SELECT id FROM weight_categories WHERE tournament_id=? AND name=?",
            (tid, cat_name)).fetchone()
        if not row:
            cid = db.add_category(tid, cat_name, _parse_weight(cat_name),
                                  cat_meta.get("hand") or "Обе")
        else:
            cid = row["id"]

        for hand in hands:
            hand_ms = [m for m in cat_rows if m["hand"] == hand]
            if not hand_ms:
                continue
            round0 = sorted(
                [m for m in hand_ms if m["stage"] == 0],
                key=lambda m: (m["match_order"], m["id"]))
            if not round0:
                continue

            existing_pids = {p["name"]: p["id"] for p in db.conn.execute(
                "SELECT id, name FROM participants WHERE tournament_id=? "
                "AND category_id=? AND hand=?", (tid, cid, hand))}
            pid_by_name = dict(existing_pids)

            names = _names_of(round0)
            created = 0
            for n in names:
                if n in pid_by_name:
                    continue
                pid_by_name[n] = db.add_participant(
                    tid, n, _parse_weight(cat_name), "", cid, hand=hand,
                    athlete_id=athlete_by_name.get(n))
                created += 1

            engine = app.SingleEliminationEngine(db)
            local = db.get_matches(cid, hand)
            if not local:
                engine.generate_bracket(
                    tid, cid, hand, [pid_by_name[n] for n in names])

            # 1-й проход: точно по (stage, match_order) — быстрый путь.
            local_by_pos = {f"{m['stage']}/{m['match_order']}": m
                            for m in db.get_matches(cid, hand)
                            if m["bracket"] == "winners"}
            for sm in hand_ms:
                winner_name = sm.get("winner_name")
                if not winner_name:
                    continue
                lm = local_by_pos.get(f"{sm['stage']}/{sm['match_order']}")
                if lm is None or lm["status"] != "pending" \
                        or not lm["p1_id"] or not lm["p2_id"]:
                    continue
                winner_pid = pid_by_name.get(winner_name)
                if winner_pid is None or winner_pid not in (
                        lm["p1_id"], lm["p2_id"]):
                    continue
                engine.advance_winner(lm["id"], winner_pid)

            # 2-й проход: по составу матча (страховка от дублей на сайте).
            replayed, mismatches = _replay_missing_results(
                db, engine, cid, hand, names, hand_ms, pid_by_name)
            total_mismatches += mismatches

            total = len(db.get_matches(cid, hand))
            done = db.conn.execute(
                "SELECT COUNT(*) FROM matches WHERE category_id=? AND hand=? "
                "AND status='done' AND winner_id IS NOT NULL",
                (cid, hand)).fetchone()[0]
            print(f"[restore] {cat_name} / {hand}: участников "
                  f"{len(pid_by_name)} (+{created}), матчей {total}, "
                  f"результатов {done}, дозаписано {replayed}")

    if total_mismatches:
        print(f"[restore] ВНИМАНИЕ: {total_mismatches} расхождений — "
              "см. строки выше")
    else:
        print("[restore] готово: результаты сверены со сайтом")
    return 0


if __name__ == "__main__":
    sys.exit(main())