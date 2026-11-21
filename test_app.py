import os
import json
from fastapi.testclient import TestClient
from main import app, WEBHOOK_PASSPHRASE

client = TestClient(app)

print("1. Testing GET /health ...")
r = client.get("/health")
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
print("   /health response:", r.json())

print("\n2. Testing GET /status (querying Delta Demo balance & positions) ...")
r = client.get("/status")
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
status_data = r.json()
print("   Success:", status_data["success"])
print("   Wallet net equity:", status_data["wallet"]["meta"]["net_equity"], "USD")
print("   Open positions count:", len(status_data["positions"]))

print("\n3. Testing POST /webhook with wrong passphrase (should be 401) ...")
r = client.post("/webhook", json={
    "action": "buy",
    "symbol": "BTCUSD",
    "passphrase": "wrong_password"
})
assert r.status_code == 401, f"Expected 401, got {r.status_code}"
print("   Correctly rejected unauthorized webhook!")

print("\n4. Testing duplicate alert protection (idempotency) ...")
from main import _recent_alerts
_recent_alerts["BTCUSD:buy:mock_alert_1"] = 1795265456.0
r = client.post("/webhook", json={
    "action": "buy",
    "symbol": "BTCUSD",
    "passphrase": WEBHOOK_PASSPHRASE,
    "alert_id": "mock_alert_1"
})
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
res = r.json()
assert "Duplicate alert ignored" in res["message"]
print("   Duplicate alert correctly detected and suppressed without re-placing order!")

print("\nAll application tests PASSED perfectly!")
