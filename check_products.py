import os
import requests
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org")

resp = requests.get(f"{BASE_URL}/v2/products")
if resp.ok:
    products = resp.json().get("result", [])
    perps = [p for p in products if "BTC" in p.get("symbol", "") and "perpetual" in p.get("contract_type", "")]
    for p in perps:
        print(f"ID: {p.get('id')}, Symbol: {p.get('symbol')}, Type: {p.get('contract_type')}, Contract Value: {p.get('contract_value')}, Tick Size: {p.get('tick_size')}")
