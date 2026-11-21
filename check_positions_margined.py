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

def get_margined():
    path = "/v2/positions/margined"
    method = "GET"
    timestamp = str(int(time.time()))
    signature_data = method + timestamp + path
    signature = hmac.new(API_SECRET.encode(), signature_data.encode(), hashlib.sha256).hexdigest()

    headers = {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }
    r = requests.get(BASE_URL + path, headers=headers)
    print("Margined -> Status:", r.status_code, "Body:", r.text)

get_margined()
