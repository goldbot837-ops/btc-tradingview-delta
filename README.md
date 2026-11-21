# TradingView to Delta Exchange Demo Automation Bot

Automated 24/7 trading bot connecting TradingView webhook alerts to Delta Exchange Demo (India/Global Testnet).

## Features
- **Delta REST API v2 Integration**: Automated HMAC-SHA256 request signing.
- **Deduplication Protection**: Suppresses duplicate alerts within a 30-second window to prevent double entries.
- **Position Reversal Support**: When a BUY signal arrives, it closes short positions first before opening LONG; when a SELL signal arrives, it closes long positions before opening SHORT.
- **Health Check & Monitoring**: `/health` endpoint for 24/7 uptime monitoring and `/status` to inspect wallet equity and open positions.
- **Secure Credentials**: API Keys, Secrets, and Webhook passphrases are strictly read from environment variables.

---

## Project Structure
- `delta_client.py`: Core client for Delta Exchange API (balances, positions, orders).
- `main.py`: FastAPI webhook server listening on `/webhook`, `/health`, and `/status`.
- `requirements.txt`: Python package requirements.
- `render.yaml`: Render deployment configuration.
- `test_delta_connection.py`: CLI script to test Delta API credentials.
- `test_app.py`: Comprehensive test suite for endpoints, authentication, and deduplication.

---

## TradingView Alert Configuration

1. Open your Bitcoin chart on TradingView with the `SVMKR_UT_HMA_ORB` indicator applied.
2. Click **Create Alert**:
   - **For BUY Alert**:
     - Condition: `SVMKR_UT_HMA_ORB` -> `UT Long`
     - Trigger: `Once Per Bar Close`
     - Notifications tab: Check `Webhook URL` -> `https://<YOUR-RENDER-APP>.onrender.com/webhook`
     - Message:
       ```json
       {
         "action": "buy",
         "symbol": "BTCUSD",
         "passphrase": "your_webhook_passphrase",
         "alert_id": "{{timenow}}"
       }
       ```
   - **For SELL Alert**:
     - Condition: `SVMKR_UT_HMA_ORB` -> `UT Short`
     - Trigger: `Once Per Bar Close`
     - Notifications tab: Check `Webhook URL` -> `https://<YOUR-RENDER-APP>.onrender.com/webhook`
     - Message:
       ```json
       {
         "action": "sell",
         "symbol": "BTCUSD",
         "passphrase": "your_webhook_passphrase",
         "alert_id": "{{timenow}}"
       }
       ```
