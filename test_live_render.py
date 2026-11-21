import requests
import json

base_url = "https://btc-tradingview-delta.onrender.com"

print("1. Testing Live /health ...")
r_health = requests.get(f"{base_url}/health", timeout=15)
print("Health Status:", r_health.status_code, r_health.text)

print("\n2. Testing Live /status (querying Delta Exchange Demo via Render!) ...")
r_status = requests.get(f"{base_url}/status", timeout=15)
print("Status Code:", r_status.status_code)
print("Status Response:", json.dumps(r_status.json(), indent=2))
