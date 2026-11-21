import os
import time
import logging
import threading
from typing import Dict, Any
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

from delta_client import DeltaExchangeClient
from market_engine import MarketEngine

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("webhook_server")

DELTA_API_KEY = os.getenv("DELTA_API_KEY", "")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "")
DELTA_BASE_URL = os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org")
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "")
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSD")
DEFAULT_ORDER_SIZE = int(os.getenv("DEFAULT_ORDER_SIZE", "1"))
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "reversal").lower()

app = Flask(__name__)

# Initialize Delta Client
delta_client = DeltaExchangeClient(
    api_key=DELTA_API_KEY,
    api_secret=DELTA_API_SECRET,
    base_url=DELTA_BASE_URL
)

# Autonomous Real-Time Market Streaming Engine
engine = MarketEngine(
    delta_client=delta_client,
    symbol=DEFAULT_SYMBOL,
    interval=TIMEFRAME,
    order_size=DEFAULT_ORDER_SIZE
)

_engine_started = False
_engine_lock = threading.Lock()

def ensure_engine_started():
    global _engine_started
    if not _engine_started:
        with _engine_lock:
            if not _engine_started:
                engine.start()
                _engine_started = True

@app.before_request
def startup_check():
    ensure_engine_started()

# In-memory deduplication cache for manual webhook calls
_recent_alerts: Dict[str, float] = {}
DEDUP_WINDOW_SECONDS = 30

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Autonomous BTC Trading Bot - Live</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #334155; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 20px; }
        .badge { background: #22c55e; color: #fff; padding: 4px 12px; border-radius: 9999px; font-weight: bold; font-size: 14px; }
        .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }
        .stat-box { background: #0f172a; padding: 15px; border-radius: 8px; border: 1px solid #334155; }
        .stat-label { font-size: 13px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
        .stat-val { font-size: 24px; font-weight: bold; margin-top: 5px; color: #38bdf8; }
        .signal-buy { color: #4ade80; }
        .signal-sell { color: #f87171; }
        .signal-hold { color: #fbbf24; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #334155; font-size: 14px; }
        th { color: #94a3b8; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h2 style="margin:0;">Autonomous BTC Bot (Delta Demo)</h2>
                    <small style="color: #94a3b8;">Indicator: SVMKR_UT_HMA_ORB (Key: 2, ATR: 1)</small>
                </div>
                <div class="badge">● LIVE STREAMING</div>
            </div>
            <div class="grid">
                <div class="stat-box">
                    <div class="stat-label">Live BTC Price (Real-Time Tick)</div>
                    <div class="stat-val">${{ status.live_btc_price }}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Trailing Stop (UT Bot)</div>
                    <div class="stat-val">${{ status.current_trailing_stop }}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Timeframe / Symbol</div>
                    <div class="stat-val" style="color:#e2e8f0;">{{ status.interval }} / {{ status.symbol }}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Latest Indicator Signal</div>
                    <div class="stat-val {% if status.last_signal == 'BUY' %}signal-buy{% elif status.last_signal == 'SELL' %}signal-sell{% else %}signal-hold{% endif %}">
                        {{ status.last_signal }}
                    </div>
                </div>
            </div>
            <p style="font-size: 12px; color: #64748b; margin-top: 15px; margin-bottom: 0;">
                Auto-refreshes every 5 seconds. Connected via live tick WebSocket. Last tick received: {{ status.last_tick_time or 'Connecting...' }}
            </p>
        </div>

        <div class="card">
            <h3 style="margin-top:0;">Trade Execution Log</h3>
            {% if status.trade_history %}
            <table>
                <thead>
                    <tr>
                        <th>Time (UTC)</th>
                        <th>Action</th>
                        <th>Price</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for t in status.trade_history %}
                    <tr>
                        <td>{{ t.timestamp }}</td>
                        <td style="font-weight:bold; color: {% if t.action == 'BUY' %}#4ade80{% else %}#f87171{% endif %};">{{ t.action }}</td>
                        <td>${{ t.price }}</td>
                        <td>{{ t.status }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #94a3b8; font-size: 14px; margin: 0;">Listening for live candle closes... Trades will appear here automatically.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def root():
    ensure_engine_started()
    status = engine.get_status()
    return render_template_string(DASHBOARD_HTML, status=status)

@app.route("/health", methods=["GET"])
def health_check():
    ensure_engine_started()
    return jsonify({
        "status": "ok",
        "live_price": engine.current_tick_price,
        "timestamp": int(time.time())
    }), 200

@app.route("/status", methods=["GET"])
def account_status():
    ensure_engine_started()
    try:
        balance = delta_client.get_wallet_balances()
        positions = delta_client.get_positions()
        engine_status = engine.get_status()
        return jsonify({
            "success": True,
            "engine": engine_status,
            "wallet": balance,
            "positions": positions
        }), 200
    except Exception as e:
        logger.error(f"Failed to query status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def receive_tradingview_alert():
    ensure_engine_started()
    data = request.get_json(force=True, silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    if WEBHOOK_PASSPHRASE and data.get("passphrase") != WEBHOOK_PASSPHRASE:
        return jsonify({"error": "Invalid passphrase"}), 401

    action = str(data.get("action", "")).strip().lower()
    if action not in ["buy", "sell"]:
        return jsonify({"error": f"Invalid action: {action}. Must be 'buy' or 'sell'."}), 400

    symbol = str(data.get("symbol") or DEFAULT_SYMBOL).strip().upper()
    try:
        order_size = int(data.get("size")) if data.get("size") else DEFAULT_ORDER_SIZE
    except (ValueError, TypeError):
        order_size = DEFAULT_ORDER_SIZE

    now = time.time()
    alert_id = data.get("alert_id") or data.get("bar_time") or f"{action}_{int(now // DEDUP_WINDOW_SECONDS)}"
    dedup_key = f"{symbol}:{action}:{alert_id}"

    if dedup_key in _recent_alerts:
        return jsonify({
            "success": True,
            "message": f"Duplicate alert ignored ({now - _recent_alerts[dedup_key]:.1f}s ago)."
        }), 200

    _recent_alerts[dedup_key] = now

    try:
        close_result = delta_client.close_position(symbol)
        order_result = delta_client.place_order(
            symbol=symbol,
            size=order_size,
            side=action,
            order_type="market_order"
        )
        return jsonify({
            "success": True,
            "action": action,
            "order": order_result
        }), 200
    except Exception as e:
        logger.error(f"Webhook execution error: {e}")
        return jsonify({"error": str(e)}), 500

# Always start engine
ensure_engine_started()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
