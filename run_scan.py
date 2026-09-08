"""Daily Pattern A scan driver. Scans the universe, returns ranked candidates.

Output: JSON + human-readable lines. Used by the cron job and by on-demand runs.
"""
import os, sys, json, csv, time, importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanner as S
importlib.reload(S)

BASE = os.path.dirname(os.path.abspath(__file__))
RESULT = os.path.join(BASE, "result.json")

FRESH_CUTOFF = 5  # only trigger days within the last trading week interest us today

# State file recording the last trading day we already reported on.
STATE_FILE = os.path.join(BASE, "last_reported.txt")


def last_trading_day(rows):
    """Return the date (str) of the most recent bar in the universe's data."""
    return rows[-1][0]


def should_run(rows):
    """Return (run: bool, reason: str). Skip when the data has no NEW trading day
    since the last run (covers weekends and NSE holidays automatically)."""
    if not rows:
        return False, "no data"
    latest = last_trading_day(rows)
    if os.path.exists(STATE_FILE):
        prev = open(STATE_FILE).read().strip()
        if prev == latest:
            return False, f"no new trading data since {latest} (already reported)"
    return True, latest


def load_universe(path):
    syms = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            s = (r.get("symbol") or "").strip()
            if s:
                syms.append([s, (r.get("name") or "").strip()])
    return syms


def main(max_stocks=None, verbose=False):
    uni = load_universe(os.path.join(BASE, "universe.csv"))
    if max_stocks:
        uni = uni[:max_stocks]
    hits = []
    errors = 0
    results = hits
    t0 = time.time()
    # --- no-new-data guard (weekends + NSE holidays) ---
    # Peek at a liquid symbol to learn the latest trading day without scanning all.
    try:
        probe = S.fetch_yf(uni[0][0] if uni else "RELIANCE")
        run, reason = should_run(probe)
    except Exception:
        run, reason = True, "probe-failed-run-anyway"
    if not run:
        print(f"SKIP {reason}")
        return []
    # --- scan ---
    for s, nm in uni:
        sym = s
        try:
            rows = S.fetch_yf(sym)
        except Exception:
            errors += 1
            continue
        if not rows:
            continue
        dates = [r[0] for r in rows]
        cands = S.analyse(rows)
        for c in cands:
            # only fresh setups from the last FRESH_CUTOFF sessions
            if c["trigger_date"] not in dates:
                continue
            idx = dates.index(c["trigger_date"])
            if len(dates) - 1 - idx > FRESH_CUTOFF:
                continue
            broke, brk_date = S.check_break(rows, c["trigger_high"], idx)
            results.append({
                "symbol": s, "name": nm,
                "trigger_date": c["trigger_date"],
                "trigger_high": c["trigger_high"],
                "trigger_close": c["trigger_close"],
                "move_pct": c["move_pct"],
                "surge_ratio": c["surge_ratio"],
                "broke": broke, "break_date": brk_date,
                "vol": c["vol"],
            })
            if verbose:
                print(json.dumps(results[-1], default=str))
    # sort: broke first, then recency
    results.sort(key=lambda r: (not r["broke"], r["trigger_date"] or ""), reverse=False)
    json.dump(results, open(RESULT, "w"), indent=2, default=str)
    # record the trading day we just covered, so a same-day re-run is skipped
    try:
        open(STATE_FILE, "w").write(reason)
    except Exception:
        pass
    print(f"SCAN_DONE stocks={len(uni)} hits={len(results)} errors={errors} time={time.time()-t0:.0f}s")
    return results


if __name__ == "__main__":
    max_scan = os.environ.get("MAX_SCAN")
    r = main(int(max_scan) if max_scan else None, verbose=True)
    print("\n=== TOP / ACTIONABLE ===")
    for x in r[:12]:
        print(f"  {x['symbol'].ljust(16)} trig {x['trigger_date']} high {x['trigger_high']} "
              f"move {x['move_pct']}% surge {x['surge_ratio']}x | break:{x['broke']} "
              f"{x['break_date'] or ''}  {x['name']}")