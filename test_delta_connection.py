import os
import sys
import json
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("DELTA_API_KEY", "").strip()
API_SECRET = os.getenv("DELTA_API_SECRET", "").strip()

if not API_KEY or not API_SECRET:
    print("[ERROR] DELTA_API_KEY and DELTA_API_SECRET must be set.")
    sys.exit(1)

test_urls = [
    ("Global Demo / Testnet", "https://testnet-api.delta.exchange"),
    ("India Demo / Testnet", "https://cdn-ind.testnet.deltaex.org"),
    ("Global Live", "https://api.delta.exchange"),
    ("India Live", "https://api.india.delta.exchange")
]

def check_endpoint(name, base_url):
    path = "/v2/wallet/balances"
    method = "GET"
    timestamp = str(int(time.time()))
    signature_data = method + timestamp + path
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        signature_data.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }

    url = base_url + path
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        return resp.status_code, data
    except Exception as e:
        return None, str(e)

print(f"Testing API Key: {API_KEY[:6]}...{API_KEY[-4:]}\n")

matched = None
for name, url in test_urls:
    status_code, data = check_endpoint(name, url)
    print(f"--- Checking {name} ({url}) ---")
    print(f"Status Code: {status_code}")
    print(f"Response: {data}\n")
    if status_code == 200:
        matched = (name, url)
        break

if matched:
    print(f"===> SUCCESS! Verified connection on: {matched[0]} ({matched[1]})")
else:
    print("===> Could not authenticate on any of the endpoints. Please check error responses above.")
