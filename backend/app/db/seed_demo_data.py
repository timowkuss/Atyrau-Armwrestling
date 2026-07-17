"""Наполняет базу демо-данными для проверки публичного API (Этап 3):
несколько клубов, тренеров, спортсменов и один опубликованный турнир
с категориями, участниками, матчами, результатами и статистикой.

Запуск:
    venv/bin/python -m app.db.seed_demo_data

Идемпотентно: если демо-турнир уже есть — скрипт ничего не делает.
"""

from datetime import date

from app.db.models.athletes import Athlete
from app.db.models.categories import Category, WeightCategory
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.geo import City
from app.db.models.matches import Match
from app.db.models.results import Result
from app.db.models.statistics import AthleteStatistic
from app.db.session import SessionLocal

DEMO_COMPETITION_NAME = "Кубок Атырау 2026 (демо)"


def seed_demo_data():
    db = SessionLocal()
    try:
        if db.query(Competition).filter_by(name=DEMO_COMPETITION_NAME).first():
            print("Демо-данные уже загружены, пропускаю.")
            return

        atyrau = db.query(City).filter_by(name="Атырау").first()
        almaty = db.query(City).filter_by(name="Алматы").first()
        aktau = db.query(City).filter_by(name="Актау").first()

        club_1 = Club(
            name="Батыр Атырау",
            description="Клуб армрестлинга при СДЮШОР Атырау",
            city_id=atyrau.id,
            founded_year=2015,
            rating_points=340,
        )
        club_2 = Club(
            name=" Altyn Alqa",
            description="Клуб силовых единоборств Алматы",
            city_id=almaty.id,
            founded_year=2018,
            rating_points=210,
        )
        db.add_all([club_1, club_2])
        db.flush()

        coach_1 = Coach(full_name="Ануар Жаксыбеков", club_id=club_1.id, bio="МСМК по армрестлингу")
        coach_2 = Coach(full_name="Дархан Оспанов", club_id=club_2.id, bio="Тренер высшей категории")
        db.add_all([coach_1, coach_2])
        db.flush()

        athletes_data = [
            ("Ерлан Сапаров", date(1999, 3, 12), "male", club_1, coach_1, atyrau, "МС"),
            ("Нурлан Бекенов", date(2001, 7, 4), "male", club_1, coach_1, atyrau, "КМС"),
            ("Дамир Исатаев", date(1997, 11, 20), "male", club_2, coach_2, almaty, "МС"),
            ("Алишер Кенжебаев", date(2003, 1, 30), "male", club_2, coach_2, almaty, "1 разряд"),
            ("Айгерим Нурлановна", date(2000, 5, 18), "female", club_1, coach_1, atyrau, "КМС"),
            ("Динара Есенова", date(1998, 9, 9), "female", club_2, coach_2, almaty, "МС"),
            ("Бекзат Тлеубаев", date(2002, 2, 14), "male", club_1, coach_1, aktau, "1 разряд"),
            ("Максат Оразбаев", date(1995, 6, 27), "male", club_2, coach_2, aktau, "МСМК"),
        ]

        athletes = []
        for full_name, birth_date, gender, club, coach, city, rank in athletes_data:
            athlete = Athlete(
                full_name=full_name,
                birth_date=birth_date,
                gender=gender,
                club_id=club.id,
                coach_id=coach.id,
                city_id=city.id,
                rank=rank,
            )
            db.add(athlete)
            athletes.append(athlete)
        db.flush()

        for athlete in athletes:
            db.add(AthleteStatistic(athlete_id=athlete.id))
        db.flush()

        wc_80_male = db.query(WeightCategory).filter_by(name="до 80 кг", gender="male").first()
        wc_65_female = db.query(WeightCategory).filter_by(name="до 65 кг", gender="female").first()

        competition = Competition(
            name=DEMO_COMPETITION_NAME,
            date=date(2026, 5, 16),
            location_city_id=atyrau.id,
            organizer="Федерация армрестлинга Атырау",
            description="Ежегодный региональный турнир по армрестлингу.",
            status="published",
        )
        db.add(competition)
        db.flush()

        category_male = Category(
            competition_id=competition.id,
            weight_category_id=wc_80_male.id if wc_80_male else None,
            hand="Правая",
            name="Мужчины до 80 кг, правая рука",
        )
        category_female = Category(
            competition_id=competition.id,
            weight_category_id=wc_65_female.id if wc_65_female else None,
            hand="Правая",
            name="Женщины до 65 кг, правая рука",
        )
        db.add_all([category_male, category_female])
        db.flush()

        male_athletes = [a for a in athletes if a.gender == "male"][:4]
        female_athletes = [a for a in athletes if a.gender == "female"][:2]

        male_participants = []
        for i, athlete in enumerate(male_athletes):
            cp = CompetitionParticipant(
                competition_id=competition.id,
                athlete_id=athlete.id,
                category_id=category_male.id,
                seed=i + 1,
            )
            db.add(cp)
            male_participants.append(cp)

        female_participants = []
        for i, athlete in enumerate(female_athletes):
            cp = CompetitionParticipant(
                competition_id=competition.id,
                athlete_id=athlete.id,
                category_id=category_female.id,
                seed=i + 1,
            )
            db.add(cp)
            female_participants.append(cp)
        db.flush()

        # Простая демонстрационная сетка (не полный движок DE — это остаётся
        # в десктопе): полуфиналы + финал для мужской категории.
        semi1 = Match(
            competition_id=competition.id,
            category_id=category_male.id,
            hand="Правая",
            round_name="Полуфинал 1",
            bracket="winners",
            match_order=1,
            p1_id=male_participants[0].id,
            p2_id=male_participants[1].id,
            winner_id=male_participants[0].id,
            status="finished",
        )
        semi2 = Match(
            competition_id=competition.id,
            category_id=category_male.id,
            hand="Правая",
            round_name="Полуфинал 2",
            bracket="winners",
            match_order=2,
            p1_id=male_participants[2].id,
            p2_id=male_participants[3].id,
            winner_id=male_participants[2].id,
            status="finished",
        )
        db.add_all([semi1, semi2])
        db.flush()

        final = Match(
            competition_id=competition.id,
            category_id=category_male.id,
            hand="Правая",
            round_name="Финал",
            bracket="winners",
            match_order=3,
            p1_id=male_participants[0].id,
            p2_id=male_participants[2].id,
            winner_id=male_participants[0].id,
            status="finished",
        )
        db.add(final)
        db.flush()

        final_female = Match(
            competition_id=competition.id,
            category_id=category_female.id,
            hand="Правая",
            round_name="Финал",
            bracket="winners",
            match_order=1,
            p1_id=female_participants[0].id,
            p2_id=female_participants[1].id,
            winner_id=female_participants[0].id,
            status="finished",
        )
        db.add(final_female)
        db.flush()

        # Итоговые результаты
        db.add_all(
            [
                Result(
                    competition_id=competition.id,
                    category_id=category_male.id,
                    competition_participant_id=male_participants[0].id,
                    place=1,
                    medal="gold",
                    points=100,
                ),
                Result(
                    competition_id=competition.id,
                    category_id=category_male.id,
                    competition_participant_id=male_participants[2].id,
                    place=2,
                    medal="silver",
                    points=70,
                ),
                Result(
                    competition_id=competition.id,
                    category_id=category_male.id,
                    competition_participant_id=male_participants[1].id,
                    place=3,
                    medal="bronze",
                    points=50,
                ),
                Result(
                    competition_id=competition.id,
                    category_id=category_male.id,
                    competition_participant_id=male_participants[3].id,
                    place=4,
                    medal="none",
                    points=20,
                ),
                Result(
                    competition_id=competition.id,
                    category_id=category_female.id,
                    competition_participant_id=female_participants[0].id,
                    place=1,
                    medal="gold",
                    points=100,
                ),
                Result(
                    competition_id=competition.id,
                    category_id=category_female.id,
                    competition_participant_id=female_participants[1].id,
                    place=2,
                    medal="silver",
                    points=70,
                ),
            ]
        )

        # Статистика победителей (упрощённо, для демонстрации, а не через
        # полноценный stats_engine.py — тот появится на Этапе 7)
        winner_stats = (
            db.query(AthleteStatistic)
            .filter(AthleteStatistic.athlete_id == male_participants[0].athlete_id)
            .first()
        )
        winner_stats.total_competitions = 1
        winner_stats.total_wins = 2
        winner_stats.total_losses = 0
        winner_stats.win_rate = 1.0
        winner_stats.right_hand_wins = 2
        winner_stats.gold_count = 1

        db.commit()
        print("Демо-данные загружены: 2 клуба, 2 тренера, 8 спортсменов, 1 турнир.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
