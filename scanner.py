"""Pattern A ("Desert" Volume Breakout) daily scanner.

Detects volume-desert -> surge + same-day price move setup from OHLCV per the
course notes, and reports whether the trigger-day High has since been broken.

Data: Yahoo Finance daily OHLCV (symbol.NS), cached on disk in ./cache.
"""
import os, json, time, datetime, urllib.request, statistics

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache")
os.makedirs(CACHE, exist_ok=True)

from datetime import datetime as _dt

# ---------- Pattern A parameters (from the notes) ----------
DESERT_LOOKBACK = 30    # look back up to 30 sessions for the quiet base
DESERT_MIN      = 15    # min quiet sessions required
SURGE_MULT      = 8.0   # trigger volume >= 8x the desert median (NARROW)
SPIKE_DOMINATES = 3.0   # trigger volume >= 3x the largest prior base bar
SPIKE = SPIKE_DOMINATES
MIN_MOVE_PCT    = 6.0   # min same-day % price move on a trigger day (NARROW)

# --- teacher's volatility/extension filter ---
VOL_WINDOW   =  22
MAX_VOL_PCT   =  4.0      # cap avg day-move
MAX_NEW_HIGHS = 2      # cap 20-day-high sessions



def fetch_yf(symbol, delay_h=6):
    """Return ascending list of [date, o, h, l, c, vol] for symbol. Cached ~delay_h."""
    cp = os.path.join(CACHE, symbol + ".json")
    cache = None
    if os.path.exists(cp):
        try:
            cache = json.load(open(cp))
        except Exception:
            cache = None
    if cache and cache.get("fetched", 0) > time.time() - delay_h * 3600:
        return cache.get("data", [])
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/{s}?"
           "range=1y&interval=1d&events=div%2Csplit").format(s=symbol + ".NS")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.load(r)
        res = j["chart"]["result"][0]
        ts, q = res["timestamp"], res["indicators"]["quote"][0]
        out = []
        for i, t in enumerate(ts):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            v = q["volume"][i]
            if o and h and l and c and v:
                d = _dt.fromtimestamp(t).date().isoformat()
                out.append([d, round(o, 2), round(h, 2), round(l, 2), round(c, 2), int(v)])
        json.dump({"fetched": time.time(), "data": out}, open(cp, "w"))
        return out
    except Exception as e:
        if cache:
            return cache.get("data", [])
        raise


def analyse(rows):
    """Detect Pattern A trigger days in ascending daily bars. Returns cands newest-first."""
    if len(rows) < DESERT_MIN + 8:
        return []
    cands = []
    n = len(rows)
    start = max(n - 14, DESERT_MIN + 3)          # can only be a trigger if >=DESERT_MIN prior bars
    for idx in range(n - 1, start - 1, -1):
        trig = rows[idx]
        prior = rows[:idx]
        if len(prior) < DESERT_MIN:
            break
        win = prior[-DESERT_LOOKBACK:]
        vols = [r[5] for r in win]
        med = statistics.median(vols)
        mx = max(vols)
        t_close, t_high, t_vol, t_date = trig[4], trig[2], trig[5], trig[0]
        prev_close = prior[-1][4]
        move_pct = (t_close / prev_close - 1) * 100
        if not (med and mx):
            continue
        if t_vol < SURGE_MULT * med:             # volume surge vs quiet base
            continue
        if t_vol < SPIKE * mx:                 # spike must dwarf the largest prior bar
            continue
        if move_pct < MIN_MOVE_PCT:            # meaningful same-day price move
            continue
        # base must be quiet: no prior bar near the spike, and no prior strong close
        min_base = min(vols)

# --- teacher filter: volatility + fresh-20day-high count over prior month ---
        w2 = prior[-VOL_WINDOW:]
        if len(w2) > 1:
            dv = [abs(w2[i][4] / w2[i-1][4] - 1) for i in range(1, len(w2))]
            avg_daily_vol = (sum(dv) / len(dv)) * 100.0
        else:
            avg_daily_vol = 0.0
        highcount = 0
        base2 = len(prior) - len(w2)
        for i in range(len(w2)):
            ref2 = rows[max(0, base2 + i - 20):base2 + i]
            if ref2 and w2[i][2] >= max(r[2] for r in ref2):
                highcount += 1
        too_volatile = avg_daily_vol > MAX_VOL_PCT
        too_extended = highcount > MAX_NEW_HIGHS
        avg_daily_vol = round(avg_daily_vol, 2)
        cands.append({
            "trigger_date": trig[0],
            "trigger_high": t_high,
            "trigger_close": t_close,
            "move_pct": round(move_pct, 2),
            "vol": t_vol,
            "med_prior_vol": int(med),
            "max_prior_vol": int(mx),
            "surge_ratio": round(t_vol / med, 1),
            "still_waiting": True,
            "avg_daily_vol": avg_daily_vol,
            "highcount": highcount,
            "too_volatile": too_volatile,
            "too_extended": too_extended,
        })
        if len(cands) >= 4:
            break
    return cands


def check_break(rows, trigger_high, trigger_idx):
    """After the trigger index, did any later day trade/close above trigger_high? -> entry confirmed."""
    for r in rows[trigger_idx + 1:]:
        if r[2] > trigger_high:            # high(ix 2) > trigger high => traded above
            return True, r[0]
    return False, None


if __name__ == "__main__":
    print("scanner module imported ok")