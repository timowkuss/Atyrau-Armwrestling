import sqlite3

conn = sqlite3.connect(r"C:\Users\kusaj\Desktop\Armwrestling\desktop-app\sync_state.db")
conn.row_factory = sqlite3.Row

# All id_map entries
print("=== id_map entries ===")
rows = conn.execute("SELECT * FROM id_map ORDER BY entity_type, local_id").fetchall()
for r in rows:
    print(f"  type={r['entity_type']:15s} local={r['local_id']:5d} remote={r['remote_id']:5d}")

print("\n=== pending_queue ===")
rows = conn.execute("SELECT * FROM pending_queue ORDER BY id").fetchall()
for r in rows:
    print(f"  id={r['id']} op={r['operation']} attempts={r['attempts']} error={r['last_error']}")
    payload = r['payload']
    if len(payload) > 200:
        payload = payload[:200] + "..."
    print(f"    payload={payload}")

conn.close()
