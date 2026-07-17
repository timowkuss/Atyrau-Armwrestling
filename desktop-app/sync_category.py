from sync.sync_manager import sync_manager as sm

sm.on_category_created(1, 3, "Senior Men 60kg Both", 60.0, "Обе")
sm.on_category_created(1, 4, "Junior Boys 50kg Both", 50.0, "Обе")

print("category 3:", sm.state.map_get("category", 3))
print("category 4:", sm.state.map_get("category", 4))