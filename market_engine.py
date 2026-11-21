import time
import json
import logging
import threading
from typing import List, Dict, Any, Optional
import requests
import websocket

logger = logging.getLogger("market_engine")

class UTBotEngine:
    """
    Mathematical translation of TradingView indicator 'SVMKR_UT_HMA_ORB' (UT Bot):
    a = 2 (UT Key Value)
    c = 1 (UT ATR Period)
    """
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
    """
    Real-time streaming engine connecting live market ticks to Delta Exchange Demo trades.
    Tracks live prices, executed orders, and realized P&L.
    """
    def __init__(self, delta_client, symbol: str = "BTCUSD", interval: str = "15m", order_size: int = 1):
        self.delta_client = delta_client
        self.symbol = symbol.upper()
        self.interval = interval.lower()
        self.order_size = int(order_size)

        self.ut_bot = UTBotEngine(key_value=2.0, atr_period=1)
        self.candles: List[List[Any]] = []
        self.current_tick_price: float = 0.0
        self.delta_mark_price: float = 0.0
        self.delta_spot_price: float = 0.0
        self.last_tick_timestamp: float = 0.0
        self.last_evaluated_candle_time: int = 0
        self.trade_history: List[Dict[str, Any]] = []

        self.running = False
        self.ws = None
        self._thread = None
        self._delta_poll_thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        self._delta_poll_thread = threading.Thread(target=self._poll_delta_ticker, daemon=True)
        self._delta_poll_thread.start()
        
        logger.info(f"MarketEngine started for {self.symbol} on {self.interval} timeframe.")

    def stop(self):
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _poll_delta_ticker(self):
        """Polls Delta Exchange's own ticker every 3 seconds to keep Delta Mark Price and Spot Price synced."""
        while self.running:
            try:
                base_url = self.delta_client.base_url
                r = requests.get(f"{base_url}/v2/tickers/{self.symbol}", timeout=4)
                if r.ok:
                    res = r.json().get("result", {})
                    self.delta_mark_price = float(res.get("mark_price", self.delta_mark_price or self.current_tick_price))
                    self.delta_spot_price = float(res.get("spot_price", self.delta_spot_price or self.current_tick_price))
                    if self.current_tick_price == 0.0:
                        self.current_tick_price = self.delta_mark_price
            except Exception as e:
                logger.debug(f"Delta ticker poll note: {e}")
            time.sleep(3)

    def get_status(self) -> Dict[str, Any]:
        # Calculate performance metrics
        closed_trades = [t for t in self.trade_history if "pnl" in t and t["pnl"] is not None]
        total_realized_pnl = sum(t["pnl"] for t in closed_trades)
        wins = sum(1 for t in closed_trades if t["pnl"] > 0)
        losses = sum(1 for t in closed_trades if t["pnl"] < 0)
        win_rate = round((wins / len(closed_trades) * 100), 1) if closed_trades else 0.0

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "live_btc_price": round(self.delta_mark_price or self.current_tick_price, 2),
            "delta_mark_price": round(self.delta_mark_price or self.current_tick_price, 2),
            "delta_spot_price": round(self.delta_spot_price or self.current_tick_price, 2),
            "current_trailing_stop": round(self.ut_bot.trailing_stop, 2),
            "last_signal": self.ut_bot.last_signal,
            "candle_count": len(self.candles),
            "last_tick_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(self.last_tick_timestamp or time.time())),
            "total_trades": len(self.trade_history),
            "closed_trades_count": len(closed_trades),
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_realized_pnl": round(total_realized_pnl, 4),
            "trade_history": list(reversed(self.trade_history[-20:]))
        }

    def _sync_history(self):
        url = "https://api.binance.us/api/v3/klines"
        binance_symbol = "BTCUSDT" if "BTC" in self.symbol else self.symbol
        params = {"symbol": binance_symbol, "interval": self.interval, "limit": 100}
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.ok:
                raw_candles = r.json()
                self.candles = raw_candles[:-1]
                self.ut_bot.compute_all(self.candles)
                if raw_candles:
                    latest_raw = raw_candles[-1]
                    self.current_tick_price = float(latest_raw[4])
                    self.last_tick_timestamp = time.time()
                logger.info(f"Synced {len(self.candles)} historical candles. Trailing stop: {self.ut_bot.trailing_stop:.2f}")
        except Exception as e:
            logger.error(f"Error syncing history: {e}")

    def execute_signal(self, action: str, price: Optional[float] = None) -> Dict[str, Any]:
        exec_price = price or self.delta_mark_price or self.current_tick_price
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
            # 1. Close opposing position first (reversal)
            close_res = self.delta_client.close_position(self.symbol)
            if close_res:
                meta = close_res.get("result", {}).get("meta_data", {})
                pnl = meta.get("pnl")
                if pnl is not None:
                    try:
                        log_entry["pnl"] = round(float(pnl), 4)
                    except Exception:
                        pass
                logger.info(f"Position closed before {action}. Close result: {close_res}")

            # 2. Open new position
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

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            k = data.get("k", {})
            if not k:
                return

            self.current_tick_price = float(k.get("c", self.current_tick_price))
            self.last_tick_timestamp = time.time()

            is_closed = k.get("x", False)
            candle_start_time = k.get("t")

            # When candle closes
            if is_closed and candle_start_time != self.last_evaluated_candle_time:
                self.last_evaluated_candle_time = candle_start_time
                closed_candle = [
                    k.get("t"),
                    k.get("o"),
                    k.get("h"),
                    k.get("l"),
                    k.get("c"),
                    k.get("v")
                ]

                if self.candles:
                    prev_candle = self.candles[-1]
                    result = self.ut_bot.update_closed_candle(closed_candle, prev_candle)
                    self.candles.append(closed_candle)
                    if len(self.candles) > 200:
                        self.candles.pop(0)

                    signal = result.get("signal", "HOLD")
                    close_price = result.get("close", self.current_tick_price)
                    stop = result.get("stop")

                    logger.info(f"[CANDLE CLOSED] Time: {time.strftime('%H:%M:%S', time.gmtime(candle_start_time / 1000))} | Close: ${close_price:.2f} | Stop: ${stop:.2f} | Signal: {signal}")

                    if signal in ["BUY", "SELL"]:
                        self.execute_signal(signal, close_price)
                else:
                    self.candles.append(closed_candle)

        except Exception as e:
            logger.error(f"Error processing tick message: {e}", exc_info=True)

    def _run_loop(self):
        while self.running:
            try:
                self._sync_history()
                binance_symbol = "btcusdt" if "BTC" in self.symbol else self.symbol.lower()
                ws_url = f"wss://stream.binance.us:9443/ws/{binance_symbol}@kline_{self.interval}"
                logger.info(f"Connecting to live tick WebSocket: {ws_url}")

                self.ws = websocket.WebSocketApp(
                    ws_url,
                    on_message=self._on_message,
                    on_error=lambda ws, err: logger.warning(f"WebSocket note: {err}"),
                    on_close=lambda ws, code, msg: logger.info("WebSocket closed. Reconnecting in 5s...")
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket loop exception: {e}")

            if self.running:
                time.sleep(5)
