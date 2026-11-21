import os
import time
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel, Field
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
# EXECUTION_MODE: "reversal" (Buy closes short & opens long; Sell closes long & opens short)
#                 "long_only" (Buy opens long; Sell only closes long, never shorts)
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "reversal").lower()

app = FastAPI(title="TradingView Delta Exchange Automation", version="1.0.0")

# In-memory deduplication cache: dict of {dedup_key: timestamp}
_recent_alerts: Dict[str, float] = {}
DEDUP_WINDOW_SECONDS = 30  # Ignore duplicate identical alerts within 30 seconds

def get_delta_client() -> DeltaExchangeClient:
    if not DELTA_API_KEY or not DELTA_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Delta Exchange API credentials are not configured in environment variables."
        )
    return DeltaExchangeClient(
        api_key=DELTA_API_KEY,
        api_secret=DELTA_API_SECRET,
        base_url=DELTA_BASE_URL
    )

class WebhookPayload(BaseModel):
    action: str = Field(..., description="'buy' or 'sell'")
    symbol: Optional[str] = Field(None, description="e.g., BTCUSD")
    size: Optional[int] = Field(None, description="Number of contracts. Defaults to DEFAULT_ORDER_SIZE if not given.")
    passphrase: Optional[str] = Field(None, description="Secret token to authenticate TradingView webhook")
    bar_time: Optional[str] = Field(None, description="Bar timestamp from TradingView, e.g., {{time}}")
    alert_id: Optional[str] = Field(None, description="Unique alert identifier, e.g., {{timenow}}")

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "TradingView to Delta Exchange Demo Bot",
        "execution_mode": EXECUTION_MODE,
        "default_symbol": DEFAULT_SYMBOL
    }

@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": int(time.time())}

@app.get("/status")
def account_status():
    """Fetches wallet balances and current positions from Delta Exchange Demo."""
    client = get_delta_client()
    try:
        balance = client.get_wallet_balances()
        positions = client.get_positions()
        return {
            "success": True,
            "wallet": balance,
            "positions": positions
        }
    except Exception as e:
        logger.error(f"Failed to query Delta status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook")
async def receive_tradingview_alert(payload: WebhookPayload, request: Request):
    logger.info(f"Received webhook: {payload.dict(exclude={'passphrase'})}")

    # 1. Authenticate Passphrase if configured
    if WEBHOOK_PASSPHRASE and payload.passphrase != WEBHOOK_PASSPHRASE:
        logger.warning("Unauthorized webhook call: Passphrase mismatch.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid passphrase")

    action = payload.action.strip().lower()
    if action not in ["buy", "sell"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid action: {payload.action}. Must be 'buy' or 'sell'.")

    symbol = (payload.symbol or DEFAULT_SYMBOL).strip().upper()
    order_size = payload.size if payload.size and payload.size > 0 else DEFAULT_ORDER_SIZE

    # 2. Duplicate Alert Protection (Idempotency)
    # Deduplication key combines symbol, action, and alert_id or bar_time
    now = time.time()
    dedup_identifier = payload.alert_id or payload.bar_time or f"{action}_{int(now // DEDUP_WINDOW_SECONDS)}"
    dedup_key = f"{symbol}:{action}:{dedup_identifier}"

    # Clean old cache entries
    expired_keys = [k for k, ts in _recent_alerts.items() if now - ts > DEDUP_WINDOW_SECONDS]
    for k in expired_keys:
        del _recent_alerts[k]

    if dedup_key in _recent_alerts:
        logger.warning(f"Duplicate alert detected and skipped: {dedup_key}")
        return {
            "success": True,
            "message": f"Duplicate alert ignored (received {now - _recent_alerts[dedup_key]:.1f}s ago).",
            "dedup_key": dedup_key
        }

    _recent_alerts[dedup_key] = now

    # 3. Execute Trade on Delta Exchange Demo
    client = get_delta_client()
    execution_log = []

    try:
        if action == "buy":
            # If reversal mode, close any open SHORT position first
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
                # In long-only mode, sell signal ONLY closes long positions
                close_result = client.close_position(symbol)
                execution_log.append({"action": "close_long_only", "result": close_result})
            else:
                # In reversal mode, close any open LONG position first
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
        return {
            "success": True,
            "action": action,
            "symbol": symbol,
            "size": order_size,
            "execution_details": execution_log
        }

    except Exception as e:
        logger.error(f"Error executing trade on Delta Exchange: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
