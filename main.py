import os
import time
import logging
from typing import Dict
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from delta_client import DeltaExchangeClient

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("webhook_server")

# Load environment configurations
DELTA_API_KEY = os.getenv("DELTA_API_KEY", "")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "")
DELTA_BASE_URL = os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org")
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "")
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSD")
DEFAULT_ORDER_SIZE = int(os.getenv("DEFAULT_ORDER_SIZE", "1"))
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "reversal").lower()

app = Flask(__name__)

# In-memory deduplication cache: dict of {dedup_key: timestamp}
_recent_alerts: Dict[str, float] = {}
DEDUP_WINDOW_SECONDS = 30  # Ignore duplicate identical alerts within 30 seconds

def get_delta_client() -> DeltaExchangeClient:
    if not DELTA_API_KEY or not DELTA_API_SECRET:
        raise RuntimeError("Delta Exchange API credentials are not configured in environment variables.")
    return DeltaExchangeClient(
        api_key=DELTA_API_KEY,
        api_secret=DELTA_API_SECRET,
        base_url=DELTA_BASE_URL
    )

@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "status": "online",
        "service": "TradingView to Delta Exchange Demo Bot",
        "execution_mode": EXECUTION_MODE,
        "default_symbol": DEFAULT_SYMBOL
    })

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "timestamp": int(time.time())}), 200

@app.route("/status", methods=["GET"])
def account_status():
    """Fetches wallet balances and current positions from Delta Exchange Demo."""
    try:
        client = get_delta_client()
        balance = client.get_wallet_balances()
        positions = client.get_positions()
        return jsonify({
            "success": True,
            "wallet": balance,
            "positions": positions
        }), 200
    except Exception as e:
        logger.error(f"Failed to query Delta status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def receive_tradingview_alert():
    data = request.get_json(force=True, silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    logger.info(f"Received webhook: { {k: v for k, v in data.items() if k != 'passphrase'} }")

    # 1. Authenticate Passphrase if configured
    if WEBHOOK_PASSPHRASE and data.get("passphrase") != WEBHOOK_PASSPHRASE:
        logger.warning("Unauthorized webhook call: Passphrase mismatch.")
        return jsonify({"error": "Invalid passphrase"}), 401

    action = str(data.get("action", "")).strip().lower()
    if action not in ["buy", "sell"]:
        return jsonify({"error": f"Invalid action: {action}. Must be 'buy' or 'sell'."}), 400

    symbol = str(data.get("symbol") or DEFAULT_SYMBOL).strip().upper()
    try:
        order_size = int(data.get("size")) if data.get("size") else DEFAULT_ORDER_SIZE
    except (ValueError, TypeError):
        order_size = DEFAULT_ORDER_SIZE

    # 2. Duplicate Alert Protection (Idempotency)
    now = time.time()
    alert_id = data.get("alert_id") or data.get("bar_time") or f"{action}_{int(now // DEDUP_WINDOW_SECONDS)}"
    dedup_key = f"{symbol}:{action}:{alert_id}"

    # Clean old cache entries
    expired_keys = [k for k, ts in _recent_alerts.items() if now - ts > DEDUP_WINDOW_SECONDS]
    for k in expired_keys:
        del _recent_alerts[k]

    if dedup_key in _recent_alerts:
        logger.warning(f"Duplicate alert detected and skipped: {dedup_key}")
        return jsonify({
            "success": True,
            "message": f"Duplicate alert ignored (received {now - _recent_alerts[dedup_key]:.1f}s ago).",
            "dedup_key": dedup_key
        }), 200

    _recent_alerts[dedup_key] = now

    # 3. Execute Trade on Delta Exchange Demo
    try:
        client = get_delta_client()
        execution_log = []

        if action == "buy":
            # Close opposing short position first (if any)
            close_result = client.close_position(symbol)
            if close_result:
                execution_log.append({"action": "close_short", "result": close_result})

            # Open LONG position
            order_result = client.place_order(
                symbol=symbol,
                size=order_size,
                side="buy",
                order_type="market_order"
            )
            execution_log.append({"action": "open_long", "result": order_result})

        elif action == "sell":
            if EXECUTION_MODE == "long_only":
                close_result = client.close_position(symbol)
                execution_log.append({"action": "close_long_only", "result": close_result})
            else:
                # Close opposing long position first (if any)
                close_result = client.close_position(symbol)
                if close_result:
                    execution_log.append({"action": "close_long", "result": close_result})

                # Open SHORT position
                order_result = client.place_order(
                    symbol=symbol,
                    size=order_size,
                    side="sell",
                    order_type="market_order"
                )
                execution_log.append({"action": "open_short", "result": order_result})

        logger.info(f"Successfully processed {action.upper()} for {symbol}: {execution_log}")
        return jsonify({
            "success": True,
            "action": action,
            "symbol": symbol,
            "size": order_size,
            "execution_details": execution_log
        }), 200

    except Exception as e:
        logger.error(f"Error executing trade on Delta Exchange: {e}", exc_info=True)
        return jsonify({"error": f"Execution error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
