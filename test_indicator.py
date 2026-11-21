import requests
import json
import time

def calculate_ut_bot(candles, a=2, c=1):
    """
    Exact Pine Script implementation of SVMKR_UT_HMA_ORB (UT Bot portion):
    a = 2 (Key value)
    c = 1 (ATR period)
    """
    signals = []
    trailing_stops = []
    
    # Initialize
    prev_stop = 0.0
    prev_close = 0.0
    
    for i, candle in enumerate(candles):
        # candle format: [timestamp, open, high, low, close, volume]
        high = float(candle[2])
        low = float(candle[3])
        close = float(candle[4])
        
        # True Range calculation
        if i == 0:
            tr = high - low
        else:
            prev_c = float(candles[i-1][4])
            tr = max(high - low, abs(high - prev_c), abs(low - prev_c))
        
        # ATR(1) = tr
        n_loss = a * tr
        src = close
        
        if i == 0:
            stop = src - n_loss
        else:
            prev_src = prev_close
            if src > prev_stop and prev_src > prev_stop:
                stop = max(prev_stop, src - n_loss)
            elif src < prev_stop and prev_src < prev_stop:
                stop = min(prev_stop, src + n_loss)
            elif src > prev_stop:
                stop = src - n_loss
            else:
                stop = src + n_loss
        
        # Crossover checks
        buy_signal = False
        sell_signal = False
        
        if i > 0:
            # crossover(ema, xATRTrailingStop) where ema = close
            above = (prev_close <= prev_stop) and (src > stop)
            below = (prev_close >= prev_stop) and (src < stop)
            
            buy_signal = (src > stop) and above
            sell_signal = (src < stop) and below
            
        signal = "BUY" if buy_signal else ("SELL" if sell_signal else "HOLD")
        signals.append({
            "timestamp": candle[0],
            "close": close,
            "stop": stop,
            "signal": signal
        })
        
        prev_stop = stop
        prev_close = close

    return signals

# Fetch latest 20 candles of BTCUSDT 15m from Binance
r = requests.get("https://api.binance.com/api/v3/klines", params={"symbol": "BTCUSDT", "interval": "15m", "limit": 20})
candles = r.json()
signals = calculate_ut_bot(candles)

print(f"Calculated UT Bot for last {len(signals)} 15m candles:")
for s in signals[-5:]:
    ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(s['timestamp'] / 1000))
    print(f"Time (UTC): {ts_str} | Close: {s['close']:.2f} | Stop: {s['stop']:.2f} | Signal: {s['signal']}")
