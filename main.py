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
INVERT_SIGNALS = os.getenv("INVERT_SIGNALS", "true").lower() in ["true", "1", "yes"]

app = Flask(__name__)

# Initialize Delta Client
delta_client = DeltaExchangeClient(
    api_key=DELTA_API_KEY,
    api_secret=DELTA_API_SECRET,
    base_url=DELTA_BASE_URL
)

# Autonomous Delta Market Engine (with Inverted Strategy)
engine = MarketEngine(
    delta_client=delta_client,
    symbol=DEFAULT_SYMBOL,
    interval=TIMEFRAME,
    order_size=DEFAULT_ORDER_SIZE,
    invert_signals=INVERT_SIGNALS
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

_recent_alerts: Dict[str, float] = {}
DEDUP_WINDOW_SECONDS = 30

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Delta Exchange - Live Trading Dashboard</title>
    <meta http-equiv="refresh" content="3">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #0b0f19;
            color: #f1f5f9;
            margin: 0;
            padding: 24px;
        }
        .container { max-width: 1080px; margin: 0 auto; }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #131b2e;
            padding: 20px 24px;
            border-radius: 16px;
            border: 1px solid #1e293b;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        .title h1 { margin: 0; font-size: 22px; font-weight: 700; color: #fff; }
        .title p { margin: 4px 0 0 0; font-size: 13px; color: #94a3b8; }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(34, 197, 94, 0.15);
            color: #4ade80;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid rgba(74, 222, 128, 0.3);
        }
        .pulse-dot {
            width: 8px;
            height: 8px;
            background: #22c55e;
            border-radius: 50%;
            box-shadow: 0 0 10px #22c55e;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
            70% { transform: scale(1.1); box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
        }

        .section-title {
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #94a3b8;
            margin: 24px 0 12px 4px;
        }

        .grid-4 {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .card {
            background: #131b2e;
            border: 1px solid #1e293b;
            border-radius: 14px;
            padding: 18px 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            transition: transform 0.15s ease, border-color 0.15s ease, background-color 0.3s ease;
        }
        .card:hover { border-color: #38bdf8; }
        
        .card-label { font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
        .card-value { font-size: 24px; font-weight: 700; color: #f8fafc; }
        .card-sub { font-size: 12px; color: #64748b; margin-top: 4px; }

        .text-green { color: #4ade80 !important; }
        .text-red { color: #f87171 !important; }
        .text-blue { color: #38bdf8 !important; }
        .text-yellow { color: #fbbf24 !important; }

        .flash-up { animation: flashGreen 0.4s ease-out; }
        .flash-down { animation: flashRed 0.4s ease-out; }
        @keyframes flashGreen { 0% { background: rgba(34, 197, 94, 0.3); } 100% { background: #131b2e; } }
        @keyframes flashRed { 0% { background: rgba(239, 68, 68, 0.3); } 100% { background: #131b2e; } }

        .position-card {
            background: #131b2e;
            border: 1px solid #1e293b;
            border-radius: 14px;
            padding: 20px;
            margin-bottom: 24px;
        }
        .pos-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-top: 14px;
        }

        .table-card {
            background: #131b2e;
            border: 1px solid #1e293b;
            border-radius: 14px;
            padding: 20px;
            overflow-x: auto;
        }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th {
            font-size: 12px;
            color: #94a3b8;
            text-transform: uppercase;
            padding: 12px 14px;
            border-bottom: 1px solid #1e293b;
        }
        td {
            padding: 14px;
            font-size: 14px;
            border-bottom: 1px solid #1e293b;
            color: #e2e8f0;
        }
        tr:last-child td { border-bottom: none; }
        .tag-buy { background: rgba(74, 222, 128, 0.15); color: #4ade80; padding: 4px 8px; border-radius: 6px; font-weight: 700; font-size: 12px; }
        .tag-sell { background: rgba(248, 113, 113, 0.15); color: #f87171; padding: 4px 8px; border-radius: 6px; font-weight: 700; font-size: 12px; }

        .footer {
            text-align: center;
            font-size: 12px;
            color: #64748b;
            margin-top: 24px;
            padding-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <div class="title">
                <h1>Delta Exchange Live Trading Dashboard</h1>
                <p>Instrument: <strong>BTCUSD Perpetual</strong> &bull; Order Execution: <strong>Delta Demo</strong></p>
            </div>
            <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <div class="badge" id="strategy-badge" style="background: rgba(234, 179, 8, 0.15); color: #fbbf24; border: 1px solid rgba(234, 179, 8, 0.3);">
                    STRATEGY: REVERSED (CONTRARIAN)
                </div>
                <div class="badge" id="ws-badge">
                    <div class="pulse-dot"></div>
                    <span id="ws-badge-text">LIVE DELTA WS: ACTIVE (0ms)</span>
                </div>
            </div>
        </div>

        <!-- SECTION 1: ACCOUNT & CAPITAL -->
        <div class="section-title">Account Balance & Realized Performance</div>
        <div class="grid-4">
            <div class="card">
                <div class="card-label">Net Equity</div>
                <div class="card-value text-blue" id="val-equity">${{ account.equity }} USD</div>
                <div class="card-sub" id="val-equity-inr">&#8377;{{ account.equity_inr }} INR approx.</div>
            </div>
            <div class="card">
                <div class="card-label">Available Margin</div>
                <div class="card-value" id="val-margin">${{ account.available_margin }} USD</div>
                <div class="card-sub">Ready for orders</div>
            </div>
            <div class="card">
                <div class="card-label">Total Realized P&L</div>
                <div class="card-value {% if engine.total_realized_pnl > 0 %}text-green{% elif engine.total_realized_pnl < 0 %}text-red{% endif %}" id="val-realized-pnl">
                    {% if engine.total_realized_pnl > 0 %}+{% endif %}${{ engine.total_realized_pnl }}
                </div>
                <div class="card-sub">Net profit/loss</div>
            </div>
            <div class="card">
                <div class="card-label">Total Trades / Win Rate</div>
                <div class="card-value text-yellow" id="val-trades">{{ engine.total_trades }} <span style="font-size:16px; color:#94a3b8;">Trades</span></div>
                <div class="card-sub" id="val-win-rate">{{ engine.wins }} Wins &bull; {{ engine.losses }} Losses &bull; {{ engine.win_rate }}% Win Rate</div>
            </div>
        </div>

        <!-- SECTION 2: LIVE POSITION -->
        <div class="section-title">Current Active Position (Delta Demo)</div>
        <div class="position-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3 style="margin:0; font-size:16px;">
                    Contract: <span style="color:#38bdf8;">{{ engine.symbol }}</span> (Perpetual Futures)
                </h3>
                <span id="pos-badge" style="font-weight:700; font-size:14px; padding: 4px 10px; border-radius:6px; background: {% if position.status == 'LONG' %}rgba(74,222,128,0.2); color:#4ade80;{% elif position.status == 'SHORT' %}rgba(248,113,113,0.2); color:#f87171;{% else %}rgba(148,163,184,0.2); color:#94a3b8;{% endif %}">
                    {{ position.status }}
                </span>
            </div>
            <div class="pos-grid">
                <div class="card" style="background:#0b0f19;">
                    <div class="card-label">Position Size</div>
                    <div class="card-value" id="pos-size">{{ position.size }} <span style="font-size:14px; color:#94a3b8;">Contracts</span></div>
                </div>
                <div class="card" style="background:#0b0f19;">
                    <div class="card-label">Entry Price</div>
                    <div class="card-value" id="pos-entry">${{ position.entry_price or '0.00' }}</div>
                </div>
                <div class="card" style="background:#0b0f19;">
                    <div class="card-label">Unrealized Floating P&L</div>
                    <div class="card-value {% if position.unrealized_pnl > 0 %}text-green{% elif position.unrealized_pnl < 0 %}text-red{% endif %}" id="pos-unrealized-pnl">
                        {% if position.unrealized_pnl > 0 %}+{% endif %}${{ position.unrealized_pnl }}
                    </div>
                </div>
                <div class="card" style="background:#0b0f19;">
                    <div class="card-label">Margin In Use</div>
                    <div class="card-value" id="pos-margin">${{ position.margin }}</div>
                </div>
            </div>
        </div>

        <!-- SECTION 3: EXACT DELTA PRICES & STRATEGY SIGNALS -->
        <div class="section-title">Live Production Delta Prices &amp; Strategy Signals</div>
        <div class="grid-4">
            <div class="card" id="card-ltp">
                <div class="card-label">Delta Last Traded Price (LTP)</div>
                <div class="card-value text-blue" id="val-delta-ltp">${{ engine.delta_ltp }}</div>
                <div class="card-sub">Real-time live tick from Delta Exchange</div>
            </div>
            <div class="card" id="card-mark">
                <div class="card-label">Delta Mark Price</div>
                <div class="card-value" id="val-delta-mark">${{ engine.delta_mark_price }}</div>
                <div class="card-sub">Liquidation index price</div>
            </div>
            <div class="card">
                <div class="card-label">Trailing Stop (UT Bot)</div>
                <div class="card-value text-yellow" id="val-trailing-stop">${{ engine.current_trailing_stop }}</div>
                <div class="card-sub">Dynamic trailing stop level</div>
            </div>
            <div class="card">
                <div class="card-label">Signal &rarr; Bot Order</div>
                <div class="card-value" id="val-signal" style="font-size: 20px;">
                    {% if engine.last_signal == 'BUY' %}
                        <span class="text-green">BUY</span> &rarr; <span class="text-red">SELL (Short)</span>
                    {% elif engine.last_signal == 'SELL' %}
                        <span class="text-red">SELL</span> &rarr; <span class="text-green">BUY (Long)</span>
                    {% else %}
                        <span class="text-yellow">{{ engine.last_signal }}</span>
                    {% endif %}
                </div>
                <div class="card-sub" id="val-strategy-sub">Reversed: Buy on Sell / Sell on Buy</div>
            </div>
        </div>

        <!-- SECTION 4: TRADE HISTORY LOG -->
        <div class="section-title">Executed Trade Log (Reversed Direction)</div>
        <div class="table-card">
            {% if engine.trade_history %}
            <table>
                <thead>
                    <tr>
                        <th>Time (UTC)</th>
                        <th>Indicator Signal</th>
                        <th>Bot Order</th>
                        <th>Fill Price</th>
                        <th>Size</th>
                        <th>Realized P&L</th>
                        <th>Status</th>
                        <th>Order ID</th>
                    </tr>
                </thead>
                <tbody id="trade-history-body">
                    {% for t in engine.trade_history %}
                    <tr>
                        <td>{{ t.timestamp }}</td>
                        <td>
                            <span class="{% if t.raw_signal == 'BUY' or (not t.raw_signal and t.action == 'SELL') %}tag-buy{% else %}tag-sell{% endif %}">
                                {{ t.raw_signal or ('BUY' if t.action == 'SELL' else 'SELL') }}
                            </span>
                        </td>
                        <td>
                            <span class="{% if t.action == 'BUY' %}tag-buy{% else %}tag-sell{% endif %}">
                                {{ t.action }} (Reversed)
                            </span>
                        </td>
                        <td>${{ t.price }}</td>
                        <td>{{ t.size }} contract</td>
                        <td class="{% if t.pnl and t.pnl > 0 %}text-green{% elif t.pnl and t.pnl < 0 %}text-red{% endif %}" style="font-weight:600;">
                            {% if t.pnl is not none %}
                                {% if t.pnl > 0 %}+{% endif %}${{ t.pnl }}
                            {% else %}
                                -
                            {% endif %}
                        </td>
                        <td><span style="color:#4ade80;">{{ t.status }}</span></td>
                        <td style="font-family:monospace; color:#94a3b8;">{{ t.order_id or '-' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #94a3b8; font-size: 14px; margin: 0; padding: 12px 0;">
                No trades executed in this session yet. Bot is actively watching Delta prices 24/7!
            </p>
            {% endif %}
        </div>

        <div class="footer" id="footer-status">
            WebSocket Active &bull; Last update: {{ engine.last_tick_time }} &bull; Source: Delta Exchange Production Stream
        </div>
    </div>

    <!-- SUB-SECOND LIVE TICK STREAMING SCRIPT -->
    <script>
    let lastLtp = null;
    let pollCount = 0;

    async function fetchLive() {
        try {
            const res = await fetch('/api/live');
            if (!res.ok) return;
            const data = await res.json();
            
            // 1. Live Prices
            const ltpElem = document.getElementById('val-delta-ltp');
            const markElem = document.getElementById('val-delta-mark');
            const stopElem = document.getElementById('val-trailing-stop');
            const sigElem = document.getElementById('val-signal');
            const cardLtp = document.getElementById('card-ltp');
            
            if (data.engine) {
                const newLtp = data.engine.delta_ltp;
                if (newLtp && ltpElem) {
                    ltpElem.textContent = '$' + Number(newLtp).toFixed(1);
                    if (lastLtp !== null && cardLtp) {
                        if (newLtp > lastLtp) {
                            cardLtp.classList.remove('flash-down');
                            cardLtp.classList.add('flash-up');
                            setTimeout(() => cardLtp.classList.remove('flash-up'), 400);
                        } else if (newLtp < lastLtp) {
                            cardLtp.classList.remove('flash-up');
                            cardLtp.classList.add('flash-down');
                            setTimeout(() => cardLtp.classList.remove('flash-down'), 400);
                        }
                    }
                    lastLtp = newLtp;
                }
                if (data.engine.delta_mark_price && markElem) {
                    markElem.textContent = '$' + Number(data.engine.delta_mark_price).toFixed(2);
                }
                if (data.engine.current_trailing_stop && stopElem) {
                    stopElem.textContent = '$' + Number(data.engine.current_trailing_stop).toFixed(2);
                }
                if (data.engine.last_signal && sigElem) {
                    const raw = data.engine.last_signal;
                    const tgt = data.engine.target_action || (raw === 'BUY' ? 'SELL (Short)' : 'BUY (Long)');
                    if (data.engine.invert_signals) {
                        const rawColor = raw === 'BUY' ? 'text-green' : 'text-red';
                        const tgtColor = tgt.startsWith('BUY') ? 'text-green' : 'text-red';
                        sigElem.innerHTML = `<span class="${rawColor}">${raw}</span> &rarr; <span class="${tgtColor}">${tgt}</span>`;
                    } else {
                        sigElem.textContent = raw;
                        sigElem.className = 'card-value ' + (raw === 'BUY' ? 'text-green' : (raw === 'SELL' ? 'text-red' : 'text-yellow'));
                    }
                }
                const footer = document.getElementById('footer-status');
                if (footer && data.engine.last_tick_time) {
                    footer.textContent = 'Live WebSocket Active • Last Tick: ' + data.engine.last_tick_time + ' • Delta Production Stream';
                }
            }

            // 2. Account & Position every 2s
            pollCount++;
            if (pollCount % 4 === 0) {
                if (data.account) {
                    const eq = document.getElementById('val-equity');
                    if (eq && data.account.equity) eq.textContent = '$' + data.account.equity + ' USD';
                    const eqInr = document.getElementById('val-equity-inr');
                    if (eqInr && data.account.equity_inr) eqInr.innerHTML = '&#8377;' + data.account.equity_inr + ' INR approx.';
                    const mg = document.getElementById('val-margin');
                    if (mg && data.account.available_margin) mg.textContent = '$' + data.account.available_margin + ' USD';
                }

                if (data.position) {
                    const posB = document.getElementById('pos-badge');
                    if (posB) {
                        posB.textContent = data.position.status;
                        posB.style.background = data.position.status === 'LONG' ? 'rgba(74,222,128,0.2)' : (data.position.status === 'SHORT' ? 'rgba(248,113,113,0.2)' : 'rgba(148,163,184,0.2)');
                        posB.style.color = data.position.status === 'LONG' ? '#4ade80' : (data.position.status === 'SHORT' ? '#f87171' : '#94a3b8');
                    }
                    const posSz = document.getElementById('pos-size');
                    if (posSz) posSz.innerHTML = data.position.size + ' <span style="font-size:14px; color:#94a3b8;">Contracts</span>';
                    const posEn = document.getElementById('pos-entry');
                    if (posEn) posEn.textContent = '$' + (data.position.entry_price || '0.00');
                    const posPnl = document.getElementById('pos-unrealized-pnl');
                    if (posPnl) {
                        const pnlVal = data.position.unrealized_pnl || 0.0;
                        posPnl.textContent = (pnlVal > 0 ? '+' : '') + '$' + pnlVal;
                        posPnl.className = 'card-value ' + (pnlVal > 0 ? 'text-green' : (pnlVal < 0 ? 'text-red' : ''));
                    }
                    const posMg = document.getElementById('pos-margin');
                    if (posMg && data.position.margin) posMg.textContent = '$' + data.position.margin;
                }
            }
        } catch (e) {
            console.error('Live stream polling error:', e);
        }
    }
    // Poll every 500ms for instant real-time tick streaming without page refresh
    setInterval(fetchLive, 500);
    </script>
</body>
</html>
"""

@app.route("/api/live", methods=["GET"])
def api_live():
    ensure_engine_started()
    engine_status = engine.get_status()

    # Cached or quick wallet & position query
    account_info = {
        "equity": "0.00",
        "equity_inr": "0.00",
        "available_margin": "0.00"
    }
    try:
        w = delta_client.get_wallet_balances()
        if isinstance(w, dict) and "meta" in w:
            account_info["equity"] = str(round(float(w["meta"].get("net_equity", 0)), 2))
        res_list = w.get("result", []) if isinstance(w, dict) else []
        for r in res_list:
            if r.get("asset_symbol") == "USD":
                account_info["available_margin"] = str(round(float(r.get("available_balance", 0)), 2))
                account_info["equity_inr"] = str(round(float(r.get("available_balance_inr", 0)), 2))
                break
    except Exception:
        pass

    pos_info = {
        "status": "FLAT",
        "size": 0,
        "entry_price": "0.00",
        "unrealized_pnl": 0.0,
        "margin": "0.00"
    }
    try:
        p = delta_client.get_position_for_symbol(DEFAULT_SYMBOL)
        if p and float(p.get("size", 0)) != 0:
            sz = float(p.get("size", 0))
            pos_info["status"] = "LONG" if sz > 0 else "SHORT"
            pos_info["size"] = int(abs(sz))
            pos_info["entry_price"] = str(round(float(p.get("entry_price", 0) or 0), 2))
            pos_info["unrealized_pnl"] = round(float(p.get("unrealized_pnl", 0) or 0), 4)
            pos_info["margin"] = str(round(float(p.get("margin", 0) or 0), 2))
    except Exception:
        pass

    return jsonify({
        "engine": engine_status,
        "account": account_info,
        "position": pos_info,
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }), 200

@app.route("/", methods=["GET"])
def root():
    ensure_engine_started()
    engine_status = engine.get_status()

    # Fetch wallet details from Delta Demo
    account_info = {
        "equity": "0.00",
        "equity_inr": "0.00",
        "available_margin": "0.00"
    }
    try:
        w = delta_client.get_wallet_balances()
        if isinstance(w, dict) and "meta" in w:
            account_info["equity"] = str(round(float(w["meta"].get("net_equity", 0)), 2))
        res_list = w.get("result", []) if isinstance(w, dict) else []
        for r in res_list:
            if r.get("asset_symbol") == "USD":
                account_info["available_margin"] = str(round(float(r.get("available_balance", 0)), 2))
                account_info["equity_inr"] = str(round(float(r.get("available_balance_inr", 0)), 2))
                break
    except Exception as e:
        logger.error(f"Error reading wallet: {e}")

    # Fetch position details from Delta Demo
    pos_info = {
        "status": "FLAT (No Open Position)",
        "size": 0,
        "entry_price": "0.00",
        "unrealized_pnl": 0.0,
        "margin": "0.00"
    }
    try:
        p = delta_client.get_position_for_symbol(DEFAULT_SYMBOL)
        if p and float(p.get("size", 0)) != 0:
            sz = float(p.get("size", 0))
            pos_info["status"] = "LONG" if sz > 0 else "SHORT"
            pos_info["size"] = int(abs(sz))
            pos_info["entry_price"] = str(round(float(p.get("entry_price", 0) or 0), 2))
            pos_info["unrealized_pnl"] = round(float(p.get("unrealized_pnl", 0) or 0), 4)
            pos_info["margin"] = str(round(float(p.get("margin", 0) or 0), 2))
    except Exception as e:
        logger.error(f"Error reading position: {e}")

    return render_template_string(
        DASHBOARD_HTML,
        engine=engine_status,
        account=account_info,
        position=pos_info
    )

@app.route("/health", methods=["GET"])
def health_check():
    ensure_engine_started()
    return jsonify({
        "status": "ok",
        "delta_ltp": engine.delta_ltp,
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

    now = time.time()
    alert_id = data.get("alert_id") or data.get("bar_time") or f"{action}_{int(now // DEDUP_WINDOW_SECONDS)}"
    dedup_key = f"{DEFAULT_SYMBOL}:{action}:{alert_id}"

    if dedup_key in _recent_alerts:
        return jsonify({
            "success": True,
            "message": f"Duplicate alert ignored ({now - _recent_alerts[dedup_key]:.1f}s ago)."
        }), 200

    _recent_alerts[dedup_key] = now

    engine.last_executed_signal = action.upper()
    trade_entry = engine.execute_signal(action)
    return jsonify({
        "success": True,
        "indicator_signal": action.upper(),
        "strategy_mode": "INVERTED" if engine.invert_signals else "STANDARD",
        "trade": trade_entry
    }), 200

ensure_engine_started()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
