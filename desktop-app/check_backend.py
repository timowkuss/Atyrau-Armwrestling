import requests, json

TOKEN = "Timowkuss"
BASE = "https://atyrau-armwrestling-production.up.railway.app/api/v1/sync"
HEADERS = {"X-Sync-Token": TOKEN, "Content-Type": "application/json"}

# 1. Check current state of match 295 via public bracket endpoint
print("=== BEFORE: bracket match 295 ===")
r = requests.get("https://atyrau-armwrestling-production.up.railway.app/api/v1/public/competitions/13/bracket")
data = r.json()
for m in data:
    if m["id"] == 295:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        break

# 2. Try PATCH directly
print("\n=== PATCH match 295 ===")
patch_data = {
    "p1_id": 19,
    "p2_id": 22,
    "status": "pending"
}
r2 = requests.patch(f"{BASE}/matches/295", json=patch_data, headers=HEADERS)
print(f"Status: {r2.status_code}")
print(f"Response: {r2.text[:500]}")

# 3. Check again after PATCH
print("\n=== AFTER: bracket match 295 ===")
r3 = requests.get("https://atyrau-armwrestling-production.up.railway.app/api/v1/public/competitions/13/bracket")
data3 = r3.json()
for m in data3:
    if m["id"] == 295:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        break

# 4. Check queue endpoint
print("\n=== QUEUE after PATCH ===")
r4 = requests.get("https://atyrau-armwrestling-production.up.railway.app/api/v1/public/competitions/13/queue")
print(json.dumps(r4.json(), indent=2, ensure_ascii=False)[:2000])
