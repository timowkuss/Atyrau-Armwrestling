import sqlite3
conn = sqlite3.connect(r"C:\Users\kusaj\Desktop\Armwrestling\desktop-app\armwrestling.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])
conn.close()
