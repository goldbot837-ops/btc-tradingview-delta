import os
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")
BASE_URL = os.getenv("DELTA_BASE_URL")

def get_positions(params):
    import urllib.parse
    query_string = "?" + urllib.parse.urlencode(params) if params else ""
    path = "/v2/positions"
    method = "GET"
    timestamp = str(int(time.time()))
    signature_data = method + timestamp + path + query_string
    signature = hmac.new(API_SECRET.encode(), signature_data.encode(), hashlib.sha256).hexdigest()

    headers = {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }
    r = requests.get(BASE_URL + path + query_string, headers=headers)
    print("Params:", params, "-> Status:", r.status_code, "Body:", r.text)

get_positions({"underlying_asset_symbol": "BTC"})
get_positions({"product_id": 84})
