"""Post the Pattern A scan results (result.json) to Telegram.
Used by the GitHub Actions daily runner (Option C). Reads result.json written
by run_scan.py and sends a concise brief to the user's chat. Sends nothing's
not applicable here — the workflow gates on SKIP before calling this.

Requires env var TELEGRAM_BOT_TOKEN (GitHub Actions secret).
"""
import os, json, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = "8991530893"   # user's Telegram chat

def fmt_date(iso):
    # 2026-09-04 -> 04-Sep-26
    m = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
         "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}
    try:
        y,mo,d = iso.split("-")
        return f"{d}-{m[mo]}-{y[2:]}"
    except Exception:
        return iso

def main():
    with open(os.path.join(BASE, "result.json")) as f:
        res = json.load(f)
    if not res:
        print("NO_HITS no message")
        return
    waiting = sorted([x for x in res if not x["broke"]], key=lambda r: -r["surge_ratio"])
    broke   = [x for x in res if x["broke"]]
    lines = ["Pattern A scan (NARROW: >=6% move, >=8x surge) - waiting stocks", ""]
    if not waiting:
        lines.append("No waiting setups right now.")
    else:
        lines.append("STILL WAITING / not yet activated (no entry yet - wait for break above trigger High):")
        for x in waiting[:10]:
            lines.append("- %s: trig %s, +%.1f%%, %.0fx vol, High %.2f" % (
                x["symbol"], fmt_date(x["trigger_date"]), x["move_pct"],
                x["surge_ratio"], x["trigger_high"]))
    # Note: broke/activated entries intentionally omitted per user's preference.
    lines += ["",
              "RULE: enter only above the HIGH of the trigger day; a post-spike pullback is normal.",
              "Uses traded volume, not the delivery screen - confirm delivery % in StockEdge."]
    text = "\n".join(lines)
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    print("SENT", body[:120])

if __name__ == "__main__":
    main()