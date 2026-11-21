import os
import json
import time
from dotenv import load_dotenv
from delta_client import DeltaExchangeClient

load_dotenv()

API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")
BASE_URL = os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org")
SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSD")

print(f"Initializing Delta Client for {SYMBOL} on {BASE_URL}...")
client = DeltaExchangeClient(api_key=API_KEY, api_secret=API_SECRET, base_url=BASE_URL)

# Step 1: Check initial position
initial_pos = client.get_position_for_symbol(SYMBOL)
print(f"Initial open position for {SYMBOL}: {initial_pos}")

# Step 2: Place 1 Market BUY order
print("\n>>> 1. Placing 1-contract Market BUY order on Demo...")
buy_res = client.place_order(symbol=SYMBOL, size=1, side="buy", order_type="market_order")
print("BUY order result:", json.dumps(buy_res, indent=2))

time.sleep(2)

# Step 3: Verify position is open
pos_after_buy = client.get_position_for_symbol(SYMBOL)
print(f"\n>>> 2. Verified Position After BUY: {pos_after_buy}")

time.sleep(1)

# Step 4: Close position
print(f"\n>>> 3. Closing position on {SYMBOL}...")
close_res = client.close_position(SYMBOL)
print("Close result:", json.dumps(close_res, indent=2))

time.sleep(2)

# Step 5: Verify position is closed
pos_after_close = client.get_position_for_symbol(SYMBOL)
print(f"\n>>> 4. Verified Position After Close: {pos_after_close}")

if not pos_after_close or float(pos_after_close.get("size", 0)) == 0:
    print("\n[VERIFICATION SUCCESS] End-to-end order placement and position closing verified on Delta Demo!")
else:
    print("\n[WARNING] Position still has remaining size:", pos_after_close)
