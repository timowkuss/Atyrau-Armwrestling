"""Фикс: исправляет статус пустых матчей с 'pending' на 'waiting'."""
import sqlite3

conn = sqlite3.connect(r"C:\Users\kusaj\Desktop\Armwrestling\desktop-app\armwrestling.db")

# Находим все матчи, у которых нет обоих игроков, но статус "pending"
rows = conn.execute("""
    SELECT id, category_id, hand, bracket, round_name, p1_id, p2_id, status
    FROM matches
    WHERE status = 'pending' AND (p1_id IS NULL OR p2_id IS NULL)
""").fetchall()

print(f"Найдено {len(rows)} матчей с неверным статусом:")
for r in rows:
    print(f"  id={r[0]} cat={r[1]} {r[2]} bracket={r[3]} round={r[4]} p1={r[5]} p2={r[6]} status={r[7]}")

if rows:
    confirm = input("Исправить статус с 'pending' на 'waiting'? (y/n): ")
    if confirm.lower() == 'y':
        conn.execute("""
            UPDATE matches SET status='waiting'
            WHERE status='pending' AND (p1_id IS NULL OR p2_id IS NULL)
        """)
        conn.commit()
        print(f"Исправлено {conn.total_changes} матчей")
    else:
        print("Отменено")
else:
    print("Нет матчей для исправления")

conn.close()
