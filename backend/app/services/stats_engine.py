"""Пересчёт агрегированной статистики спортсменов (athlete_statistics).

Считается из фактических данных завершённых турниров:
- total_competitions  — число завершённых турниров с участием;
- total_wins/losses   — по сыгранным матчам (status=done, без bye), отдельно
  по рукам (left/right);
- win_rate            — wins / (wins + losses), 0 если матчей нет;
- gold/silver/bronze  — число мест 1/2/3 в категориях завершённых турниров
  (место пересчитывается из матчей через _category_standings, а не из
  сохранённой таблицы results — она могла остаться от более ранней версии);

Эло не трогаем: оно накапливается отдельно, apply_match_result() при каждом
сыгранном матче. Спортсмены с is_manual_override=True пересчёту не
подвергаются (ручные правки админа сохраняются).

Вызывается после завершения турнира (finalize_competition) и при старте
приложения — чтобы данные уже завершённых турниров починились автоматически.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic
from app.services.club_rating import _category_standings


def _hand(hand: str) -> str | None:
    h = (hand or "").strip().lower()
    if h.startswith("лев"):
        return "left"
    if h.startswith("прав"):
        return "right"
    return None


def recalculate_for(db: Session, athlete_id: int) -> bool:
    """Пересчитывает статистику одного спортсмена. Возвращает True, если
    данные были пересчитаны (False — ручной оверрайд или нет данных)."""
    stats = (
        db.query(AthleteStatistic)
        .filter(AthleteStatistic.athlete_id == athlete_id)
        .first()
    )
    if stats is None:
        stats = AthleteStatistic(athlete_id=athlete_id)
        db.add(stats)
    if stats.is_manual_override:
        return False

    completed_ids = [
        cid
        for (cid,) in db.query(Competition.id)
        .filter(Competition.status == "completed")
        .all()
    ]
    if not completed_ids:
        return False

    participants = (
        db.query(CompetitionParticipant)
        .filter(
            CompetitionParticipant.athlete_id == athlete_id,
            CompetitionParticipant.competition_id.in_(completed_ids),
        )
        .all()
    )
    if not participants:
        return False

    participant_ids = [p.id for p in participants]
    participant_set = set(participant_ids)

    total_competitions = len({p.competition_id for p in participants})

    # ── победы/поражения по матчам ──
    matches = (
        db.query(Match)
        .filter(
            Match.competition_id.in_(completed_ids),
            Match.status == "done",
            Match.is_bye.is_(False),
            Match.winner_id.isnot(None),
            or_(Match.p1_id.in_(participant_ids), Match.p2_id.in_(participant_ids)),
        )
        .all()
    )

    total_wins = total_losses = 0
    lw = ll = rw = rl = 0
    for m in matches:
        hand = _hand(m.hand)
        won = m.winner_id in participant_set
        if won:
            total_wins += 1
            if hand == "left":
                lw += 1
            elif hand == "right":
                rw += 1
        else:
            total_losses += 1
            if hand == "left":
                ll += 1
            elif hand == "right":
                rl += 1

    # ── медали по местам в категориях завершённых турниров ──
    standings_cache: dict[tuple[int, int], dict[int, int]] = {}
    gold = silver = bronze = 0
    for p in participants:
        key = (p.competition_id, p.category_id)
        if key not in standings_cache:
            comp = db.get(Competition, p.competition_id)
            cat = db.get(Category, p.category_id)
            if comp is None or cat is None:
                standings_cache[key] = {}
            else:
                standings_cache[key] = {
                    s["participant_id"]: s["place"]
                    for s in _category_standings(db, comp, cat)
                }
        place = standings_cache[key].get(p.id)
        if place == 1:
            gold += 1
        elif place == 2:
            silver += 1
        elif place == 3:
            bronze += 1

    win_rate = round(total_wins / (total_wins + total_losses), 3) if (total_wins + total_losses) else 0.0

    stats.total_competitions = total_competitions
    stats.total_wins = total_wins
    stats.total_losses = total_losses
    stats.win_rate = win_rate
    stats.left_hand_wins = lw
    stats.left_hand_losses = ll
    stats.right_hand_wins = rw
    stats.right_hand_losses = rl
    stats.gold_count = gold
    stats.silver_count = silver
    stats.bronze_count = bronze
    return True


def recalculate_all(db: Session) -> int:
    """Пересчитывает статистику всех спортсменов (кроме ручных оверрайдов).
    Возвращает число пересчитанных. Коммитит в конце."""
    athlete_ids = [aid for (aid,) in db.query(Athlete.id).all()]
    count = 0
    for aid in athlete_ids:
        if recalculate_for(db, aid):
            count += 1
    db.commit()
    return count
