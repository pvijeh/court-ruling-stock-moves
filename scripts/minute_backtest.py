"""What a stock did in the minutes after a court ruling hit the docket.

For each reviewed ruling in data/lawsuit_moves_reviewed.csv that has an exact filing time,
pull one-minute bars from Polygon.io (free plan: about 2 years back,
5 requests a minute) and measure the price before the filing, 1/5/15/60
minutes after, and at the close of the session the news first traded in.

Needs POLYGON_API_KEY in the environment. Responses are cached by symbol
and date range (the key never goes into a file name).

Output: data/minute_backtest.csv
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = Path.home() / "work" / "altdata" / "cache" / "polygon"
ET = ZoneInfo("America/New_York")
EARLIEST = date.today() - timedelta(days=729)
OFFSETS = (1, 5, 15, 60)
_last = 0.0


def bars(sym: str, start: date, end: date) -> list[dict]:
    """One-minute bars (all sessions) for sym between two dates, ET times."""
    global _last
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"{sym}_{start}_{end}.json"
    if key.exists():
        raw = json.loads(key.read_text())
    else:
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/{start}/{end}"
        )
        params = {"adjusted": "true", "sort": "asc", "limit": 50000}
        params["apiKey"] = os.environ["POLYGON_API_KEY"]
        for _ in range(4):
            wait = _last + 12.5 - time.time()
            if wait > 0:
                time.sleep(wait)
            _last = time.time()
            r = requests.get(url, params=params, timeout=60)
            if r.status_code != 429:
                break
        raw = r.json()
        if raw.get("status") not in ("OK", "DELAYED"):
            print(sym, start, raw.get("status"), raw.get("message"), file=sys.stderr)
            return []
        key.write_text(json.dumps(raw))
    out = []
    for b in raw.get("results") or []:
        t = datetime.fromtimestamp(b["t"] / 1000, ET)
        out.append({"t": t, "c": b["c"], "v": b["v"]})
    return out


def session_close(bs: list[dict], day: date) -> dict | None:
    regular = [b for b in bs if b["t"].date() == day and b["t"].hour < 16]
    return regular[-1] if regular else None


def price_at(bs: list[dict], t: datetime) -> dict | None:
    """Close of the last bar that started at or before t."""
    best = None
    for b in bs:
        if b["t"] > t:
            break
        best = b
    return best


def analyse(sym: str, filed: datetime) -> dict | None:
    bs = bars(sym, filed.date() - timedelta(days=1), filed.date() + timedelta(days=5))
    if not bs:
        return None
    minute = filed.replace(second=0, microsecond=0)
    before = [b for b in bs if b["t"] < minute]
    if not before:
        return None
    p0 = before[-1]
    t = (filed.hour, filed.minute)
    in_hours = filed.weekday() < 5 and (9, 30) <= t < (16, 0)
    # outside market hours the first trades come after hours or pre-market;
    # the move is measured to the close of the next regular session
    start = next((b["t"] for b in bs if b["t"] >= minute), None)
    regular = [
        b
        for b in bs
        if start
        and b["t"] >= start
        and (9, 30) <= (b["t"].hour, b["t"].minute) < (16, 0)
    ]
    if start is None or not regular:
        return None
    react_day = regular[0]["t"].date()
    close = session_close(bs, react_day)
    if close is None:
        return None
    row = {
        "symbol": sym,
        "filed_et": filed.isoformat(),
        "in_market_hours": in_hours,
        "reaction_start_et": start.isoformat(),
        "price_before": p0["c"],
        "price_before_et": p0["t"].isoformat(),
        "close_price": close["c"],
        "move_to_close_pct": round(100 * (close["c"] / p0["c"] - 1), 2),
    }
    total = close["c"] - p0["c"]
    for k in OFFSETS:
        p = price_at(bs, start + timedelta(minutes=k))
        row[f"price_plus_{k}m"] = p["c"] if p else ""
        row[f"move_left_after_{k}m_pct"] = (
            round(100 * (close["c"] - p["c"]) / total, 1) if p and total else ""
        )
        row[f"move_from_plus_{k}m_to_close_pct"] = (
            round(100 * (close["c"] / p["c"] - 1), 2) if p else ""
        )
    window = [b["v"] for b in before[-60:]]
    first = next((b for b in bs if b["t"] >= start), None)
    if first and window:
        row["first_minute_volume"] = round(first["v"])
        row["median_prior_minute_volume"] = round(statistics.median(window))
        row["volume_multiple"] = round(
            first["v"] / max(statistics.median(window), 1), 1
        )
    return row


def main() -> None:
    src = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "lawsuit_moves_reviewed.csv"
    )
    with open(src) as f:
        cases = list(csv.DictReader(f))
    rows = []
    for c in cases:
        if c.get("review_status", "ok") not in ("ok", "needs_check"):
            continue
        if c.get("clock_time_known") != "True":
            continue
        filed = datetime.fromisoformat(c["filed_et"]).astimezone(ET)
        if filed.date() < EARLIEST:
            continue
        for sym in c["tickers"].split():
            r = analyse(sym, filed)
            if r:
                r = {"case": c.get("case", ""), **r}
                rows.append(r)
                print(
                    sym,
                    r["filed_et"],
                    r["move_to_close_pct"],
                    r.get("move_left_after_1m_pct"),
                    r.get("volume_multiple"),
                    flush=True,
                )
    fields = list(rows[0]) if rows else []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with open(DATA / "minute_backtest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
