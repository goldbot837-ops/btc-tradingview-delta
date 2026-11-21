import time
import json
import logging
import threading
from typing import List, Dict, Any, Optional
import requests
import websocket

logger = logging.getLogger("market_engine")

class UTBotEngine:
    def __init__(self, key_value: float = 2.0, atr_period: int = 1):
        self.a = float(key_value)
        self.c = int(atr_period)
        self.trailing_stop = 0.0
        self.prev_close = 0.0
        self.last_signal = "HOLD"

    def compute_all(self, candles: List[List[Any]]) -> List[Dict[str, Any]]:
        results = []
        stop = 0.0
        prev_c = 0.0

        for i, c in enumerate(candles):
            high = float(c[2])
            low = float(c[3])
            close = float(c[4])

            if i == 0:
                tr = high - low
            else:
                last_c = float(candles[i - 1][4])
                tr = max(high - low, abs(high - last_c), abs(low - last_c))

            n_loss = self.a * tr
            src = close

            if i == 0:
                stop = src - n_loss
            else:
                if src > stop and prev_c > stop:
                    stop = max(stop, src - n_loss)
                elif src < stop and prev_c < stop:
                    stop = min(stop, src + n_loss)
                elif src > stop:
                    stop = src - n_loss
                else:
                    stop = src + n_loss

            buy_signal = False
            sell_signal = False
            if i > 0:
                above = (prev_c <= stop) and (src > stop)
                below = (prev_c >= stop) and (src < stop)
                buy_signal = (src > stop) and above
                sell_signal = (src < stop) and below

            sig = "BUY" if buy_signal else ("SELL" if sell_signal else "HOLD")
            results.append({
                "timestamp": c[0],
                "close": close,
                "stop": stop,
                "signal": sig
            })
            prev_c = close

        if results:
            self.trailing_stop = results[-1]["stop"]
            self.prev_close = results[-1]["close"]
            self.last_signal = results[-1]["signal"]

        return results

    def update_closed_candle(self, closed_candle: List[Any], prev_candle: List[Any]) -> Dict[str, Any]:
        high = float(closed_candle[2])
        low = float(closed_candle[3])
        close = float(closed_candle[4])
        prev_c = float(prev_candle[4])

        tr = max(high - low, abs(high - prev_c), abs(low - prev_c))
        n_loss = self.a * tr
        src = close

        old_stop = self.trailing_stop
        if src > old_stop and prev_c > old_stop:
            new_stop = max(old_stop, src - n_loss)
        elif src < old_stop and prev_c < old_stop:
            new_stop = min(old_stop, src + n_loss)
        elif src > old_stop:
            new_stop = src - n_loss
        else:
            new_stop = src + n_loss

        above = (prev_c <= old_stop) and (src > new_stop)
        below = (prev_c >= old_stop) and (src < new_stop)
        buy_signal = (src > new_stop) and above
        sell_signal = (src < new_stop) and below

        signal = "BUY" if buy_signal else ("SELL" if sell_signal else "HOLD")

        self.trailing_stop = new_stop
        self.prev_close = close
        self.last_signal = signal

        return {
            "timestamp": closed_candle[0],
            "close": close,
            "stop": new_stop,
            "signal": signal
        }


class MarketEngine:
    def __init__(self, delta_client, symbol: str = "BTCUSD", interval: str = "15m", order_size: int = 1):
        self.delta_client = delta_client
        self.symbol = symbol.upper()
        self.interval = interval.lower()
        self.order_size = int(order_size)

        self.ut_bot = UTBotEngine(key_value=2.0, atr_period=1)
        self.candles: List[List[Any]] = []
        
        # Delta Prices
        self.delta_ltp: float = 0.0          # Last Traded Price (What flashes on chart)
        self.delta_mark_price: float = 0.0   # Mark Price
        self.delta_spot_price: float = 0.0   # Spot Index Price
        
        self.last_tick_timestamp: float = 0.0
        self.last_evaluated_candle_time: int = 0
        self.trade_history: List[Dict[str, Any]] = []

        self.running = False
        self._delta_ws_thread = None
        self._delta_poll_thread = None
        self.ws = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._sync_history()
        # 1. Delta Live Native WebSocket for sub-second tick-by-tick streaming
        self._delta_ws_thread = threading.Thread(target=self._run_delta_ws, daemon=True)
        self._delta_ws_thread.start()
        # 2. Backup REST poller (activates only if WebSocket is disconnected)
        self._delta_poll_thread = threading.Thread(target=self._poll_delta_ticker, daemon=True)
        self._delta_poll_thread.start()
        logger.info(f"MarketEngine started with Live WebSocket for {self.symbol} on {self.interval} timeframe.")

    def stop(self):
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _sync_history(self):
        """Fetch historical candles directly from Delta Exchange."""
        base_url = self.delta_client.base_url
        try:
            r = requests.get(f"{base_url}/v2/history/candles", params={"symbol": self.symbol, "resolution": self.interval}, timeout=6)
            if r.ok:
                res = r.json().get("result", [])
                if res:
                    formatted = [[c.get("time"), c.get("open"), c.get("high"), c.get("low"), c.get("close"), c.get("volume")] for c in res]
                    self.candles = formatted
                    self.ut_bot.compute_all(self.candles)
                    logger.info(f"Synced {len(self.candles)} candles directly from Delta Exchange.")
        except Exception as e:
            logger.error(f"Error syncing Delta candles: {e}")

    def _run_delta_ws(self):
        """Persistent WebSocket streaming live ticks directly from Delta Exchange production."""
        while self.running:
            try:
                def on_message(ws, msg):
                    try:
                        d = json.loads(msg)
                        if d.get("type") == "v2/ticker" and d.get("symbol") == self.symbol:
                            close_p = d.get("close")
                            if close_p is not None:
                                self.delta_ltp = float(close_p)
                            mark_p = d.get("mark_price")
                            if mark_p is not None:
                                self.delta_mark_price = float(mark_p)
                            spot_p = d.get("spot_price")
                            if spot_p is not None:
                                self.delta_spot_price = float(spot_p)
                            self.last_tick_timestamp = time.time()
                    except Exception as ex:
                        logger.debug(f"Delta WS parse error: {ex}")

                def on_open(ws):
                    sub = {
                        "type": "subscribe",
                        "payload": {
                            "channels": [
                                {"name": "v2/ticker", "symbols": [self.symbol]}
                            ]
                        }
                    }
                    ws.send(json.dumps(sub))
                    logger.info(f"Subscribed to Delta Live WS ticker for {self.symbol}")

                def on_error(ws, err):
                    logger.warning(f"Delta WS error: {err}")

                self.ws = websocket.WebSocketApp(
                    "wss://socket.india.delta.exchange",
                    on_message=on_message,
                    on_open=on_open,
                    on_error=on_error
                )
                self.ws.run_forever(ping_interval=15, ping_timeout=10)
            except Exception as e:
                logger.error(f"Delta WS loop exception: {e}")
            time.sleep(2)

    def _poll_delta_ticker(self):
        """Backup poller: triggers only if WebSocket hasn't received a tick in 5 seconds."""
        while self.running:
            try:
                # If WS tick is older than 5 seconds, poll Delta Live REST directly
                if time.time() - self.last_tick_timestamp > 5:
                    r = requests.get(f"https://api.india.delta.exchange/v2/tickers/{self.symbol}", timeout=3)
                    if r.ok:
                        res = r.json().get("result", {})
                        ltp = res.get("close")
                        if ltp is not None:
                            self.delta_ltp = float(ltp)
                        self.delta_mark_price = float(res.get("mark_price", self.delta_ltp))
                        self.delta_spot_price = float(res.get("spot_price", self.delta_ltp))
                        self.last_tick_timestamp = time.time()
            except Exception as e:
                logger.debug(f"Delta ticker backup error: {e}")
            time.sleep(2)

    def get_status(self) -> Dict[str, Any]:
        closed_trades = [t for t in self.trade_history if "pnl" in t and t["pnl"] is not None]
        total_realized_pnl = sum(t["pnl"] for t in closed_trades)
        wins = sum(1 for t in closed_trades if t["pnl"] > 0)
        losses = sum(1 for t in closed_trades if t["pnl"] < 0)
        win_rate = round((wins / len(closed_trades) * 100), 1) if closed_trades else 0.0

        current_price = self.delta_ltp or self.delta_mark_price

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "live_btc_price": round(current_price, 2),
            "delta_ltp": round(self.delta_ltp, 2),
            "delta_mark_price": round(self.delta_mark_price, 2),
            "delta_spot_price": round(self.delta_spot_price, 2),
            "current_trailing_stop": round(self.ut_bot.trailing_stop, 2),
            "last_signal": self.ut_bot.last_signal,
            "candle_count": len(self.candles),
            "last_tick_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(self.last_tick_timestamp or time.time())),
            "total_trades": len(self.trade_history),
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_realized_pnl": round(total_realized_pnl, 4),
            "trade_history": list(reversed(self.trade_history[-20:]))
        }

    def execute_signal(self, action: str, price: Optional[float] = None) -> Dict[str, Any]:
        exec_price = price or self.delta_ltp or self.delta_mark_price
        logger.info(f"*** EXECUTING SIGNAL: {action.upper()} at ${exec_price:.2f} ***")
        
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "action": action.upper(),
            "price": round(exec_price, 2),
            "size": self.order_size,
            "status": "pending",
            "pnl": None
        }

        try:
            close_res = self.delta_client.close_position(self.symbol)
            if close_res:
                meta = close_res.get("result", {}).get("meta_data", {})
                pnl = meta.get("pnl")
                if pnl is not None:
                    try:
                        log_entry["pnl"] = round(float(pnl), 4)
                    except Exception:
                        pass

            order_res = self.delta_client.place_order(
                symbol=self.symbol,
                size=self.order_size,
                side=action.lower(),
                order_type="market_order"
            )
            log_entry["status"] = "FILLED"
            log_entry["order_id"] = order_res.get("result", {}).get("id")
            fill_p = order_res.get("result", {}).get("average_fill_price")
            if fill_p:
                log_entry["price"] = round(float(fill_p), 2)

            logger.info(f"Successfully placed {action.upper()} order on Delta Demo! Result: {order_res}")
        except Exception as e:
            log_entry["status"] = f"ERROR: {str(e)}"
            logger.error(f"Failed to execute {action.upper()} on Delta: {e}")

        self.trade_history.append(log_entry)
        return log_entry
