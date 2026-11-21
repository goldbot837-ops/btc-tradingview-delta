import websocket
import json
import time

received = []

def on_message(ws, message):
    data = json.loads(message)
    k = data.get("k", {})
    price = k.get("c")
    is_closed = k.get("x")
    received.append((price, is_closed))
    print(f"[LIVE TICK] BTC Price: ${price} | Candle Closed: {is_closed}")
    if len(received) >= 3:
        ws.close()

def on_error(ws, error):
    print("Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("Closed connection.")

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@kline_15m",
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

print("Connecting to live Binance BTC stream...")
ws.run_forever()
print(f"Successfully received {len(received)} live ticks!")
