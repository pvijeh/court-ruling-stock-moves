"""Would trading in the first minute after a ruling was posted have paid?

Takes every fast-alert event in data/universe/combined/cases.csv (no preset date,
posted 9:30-16:00 ET with a recorded time, not a settlement or withdrawal) from the
last ~2 years, where Polygon's free plan has 1-minute bars. For each stock-day:

- direction: long if the ruling was good for the company, short if bad
  (majority of the event's rows; mixed or unknown are skipped),
- entry: the open of the minute bar 1, 2, 5 or 15 minutes after the posting minute
  (a 30-second system would get roughly the +1 bar),
- exit: the 16:00 close,
- benchmark: the same window in XBI (drug patents) or SPY (everything else).

Costs are not measured (free data has no bid/ask), so results are shown gross and at
an assumed cost per side.

Needs POLYGON_API_KEY. Bars are cached outside the repo; the key never goes into a
file name. Output: data/universe/combined/intraday_backtest.csv
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "combined"
CACHE = Path.home() / "work" / "altdata" / "cache" / "polygon_min"
ET = ZoneInfo("America/New_York")
EARLIEST = datetime.now(tz=ET).date() - timedelta(days=725)
TIMED = {"minute", "hour", "inferred from price"}
DELAYS = (0, 1, 2, 5, 15)
WINDOW = 30
# Polygon free tier: 5 calls/minute; paid plans can set POLYGON_GAP lower
GAP = float(os.environ.get("POLYGON_GAP", "12.5"))
_last = 0.0


def fetch(sym: str, start: date, end: date) -> list[dict]:
    global _last
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"{sym}_{start}_{end}.json.gz"
    if key.exists():
        return json.loads(gzip.decompress(key.read_bytes()))
    url = f"https://api.polygon.io/v2/aggs/ticker/{sym.replace('-', '.')}/range/1/minute/{start}/{end}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    params["apiKey"] = os.environ["POLYGON_API_KEY"]
    for _ in range(5):
        wait = _last + GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        try:
            r = requests.get(url, params=params, timeout=60)
        except requests.RequestException:
            continue
        if r.status_code != 429:
            break
    js = r.json()
    if js.get("status") not in ("OK", "DELAYED"):
        print(sym, start, end, js.get("status"), js.get("message"), file=sys.stderr)
        return []
    res = js.get("results") or []
    key.write_bytes(gzip.compress(json.dumps(res).encode()))
    return res


def bars_for(sym: str, days: list[date]) -> dict[date, pd.DataFrame]:
    """Regular-session 1-minute bars for each day, fetching nearby days together."""
    days = sorted(set(days))
    groups, cur = [], [days[0]]
    for d in days[1:]:
        if (d - cur[0]).days <= WINDOW:
            cur.append(d)
        else:
            groups.append(cur)
            cur = [d]
    groups.append(cur)
    out = {}
    for g in groups:
        res = fetch(sym, g[0], g[-1])
        if not res:
            continue
        df = pd.DataFrame(res)
        df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(ET)
        df = df[(df["ts"].dt.time >= pd.Timestamp("09:30").time())]
        df = df[(df["ts"].dt.time < pd.Timestamp("16:00").time())]
        df["day"] = df["ts"].dt.date
        for d in g:
            day = df[df["day"] == d].set_index("ts").sort_index()
            if len(day):
                out[d] = day
    return out


def events() -> pd.DataFrame:
    c = pd.read_csv(OUT / "cases.csv", dtype=str).fillna("")
    m = (
        (c["decision_known_in_advance"] == "no")
        & (c["during_market_hours"] == "yes")
        & c["time_precision"].isin(TIMED)
        & ~c["outcome"].isin(["settled", "withdrawn"])
        & (c["decision_date"] >= str(EARLIEST))
        & (c["ticker"] != "")
        & (c["dup_of_category"] == "")
    )
    c = c[m].copy()
    c["t"] = pd.to_datetime(c["first_public_time_et"].str[:16], errors="coerce")
    c = c[c["t"].notna()]
    rows = []
    for key, g in c.groupby("event_key"):
        good = (g["outcome_for_company"] == "good").sum()
        bad = (g["outcome_for_company"] == "bad").sum()
        direction = 1 if good > bad else -1 if bad > good else 0
        first = g.sort_values("t").iloc[0]
        rows.append(
            {
                "event_key": key,
                "category": first["category"],
                "ticker": first["ticker"],
                "decision_date": first["decision_date"],
                "posted_et": first["t"].strftime("%Y-%m-%d %H:%M"),
                "case_name": first["case_name"],
                "rows": len(g),
                "good_rows": int(good),
                "bad_rows": int(bad),
                "direction": direction,
                "market_cap_usd_at_filing": pd.to_numeric(
                    first["market_cap_usd_at_filing"], errors="coerce"
                ),
                "abn_ret_decision_day": pd.to_numeric(
                    first["abn_ret_decision_day"], errors="coerce"
                ),
            }
        )
    return pd.DataFrame(rows)


def window_ret(day: pd.DataFrame, t0: pd.Timestamp, delay: int) -> float | None:
    after = day[day.index >= t0 + pd.Timedelta(minutes=delay)]
    if after.empty or (after.index[0] - t0) > pd.Timedelta(minutes=delay + 10):
        return None
    return day["c"].iloc[-1] / after["o"].iloc[0] - 1


def main() -> None:
    ev = events()
    print(f"{len(ev)} stock-day events, {ev['ticker'].nunique()} tickers", flush=True)
    ev["day"] = pd.to_datetime(ev["decision_date"]).dt.date
    bench = {"SPY": [], "XBI": []}
    for _, r in ev.iterrows():
        bench["XBI" if r["category"] == "drug_patent" else "SPY"].append(r["day"])
    bars = {b: bars_for(b, d) for b, d in bench.items() if d}
    for i, (tk, g) in enumerate(ev.groupby("ticker")):
        bars[tk] = bars_for(tk, list(g["day"]))
        if i % 20 == 0:
            print(f"  {i} tickers fetched", flush=True)
    out = []
    for _, r in ev.iterrows():
        rec = r.drop("day").to_dict()
        day = bars.get(r["ticker"], {}).get(r["day"])
        b = "XBI" if r["category"] == "drug_patent" else "SPY"
        bday = bars[b].get(r["day"])
        t0 = pd.Timestamp(r["posted_et"]).tz_localize(ET)
        rec["benchmark"] = b
        rec["minute_bars"] = day is not None
        if day is not None:
            before = day[day.index < t0]
            rec["price_before"] = before["c"].iloc[-1] if len(before) else np.nan
            rec["close"] = day["c"].iloc[-1]
            rec["dollar_vol_day"] = float((day["v"] * day["vw"]).sum())
            for d in DELAYS:
                s = window_ret(day, t0, d)
                m = window_ret(bday, t0, d) if bday is not None else None
                rec[f"ret_plus{d}"] = s
                rec[f"abn_plus{d}"] = None if s is None or m is None else s - m
                rec[f"trade_plus{d}"] = (
                    None
                    if s is None or m is None or not r["direction"]
                    else r["direction"] * (s - m)
                )
            if len(before):
                rec["move_post_to_close"] = rec["close"] / rec["price_before"] - 1
        out.append(rec)
    df = pd.DataFrame(out)
    df.to_csv(OUT / "intraday_backtest.csv", index=False)
    print(f"wrote {len(df)} rows, {int(df['minute_bars'].sum())} with minute bars")


if __name__ == "__main__":
    main()
