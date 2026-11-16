"""Stricter rerun of the intraday backtest (see docs/intraday_backtest.md).

Same trade as scripts/intraday_backtest.py (enter after posting, exit at the close,
minus SPY/XBI over the same window), on a narrower set of rulings:

- PTAB: final written decisions only (no institution denials or adverse judgments);
  other case types are kept as they are,
- company worth under $5B on the ruling day (Polygon shares outstanding near the
  ticker's first ruling, times the last price before posting),
- one side per ruling: the smallest listed company in it,
- no stock-day that already moved 3%+ against its benchmark between the 9:30 open and
  the posting time (that move is known before the trade, so this uses no hindsight).

Reads the minute bars cached by intraday_backtest.py. Needs POLYGON_API_KEY for the
share counts, cached outside the repo. Output: data/universe/combined/intraday_strict.csv
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intraday_backtest as ib

REF = Path.home() / "work" / "altdata" / "cache" / "polygon_ref"
CAP_MAX = 5e9
PRE_MOVE_MAX = 0.03
_last = 0.0


def shares(sym: str, day: str) -> tuple[float | None, float | None]:
    """(shares outstanding, market cap) from Polygon ticker details on a date."""
    global _last
    REF.mkdir(parents=True, exist_ok=True)
    p = REF / f"{sym}_{day}.json.gz"
    if p.exists():
        js = json.loads(gzip.decompress(p.read_bytes()))
    else:
        url = f"https://api.polygon.io/v3/reference/tickers/{sym.replace('-', '.')}"
        params = {"date": day, "apiKey": os.environ["POLYGON_API_KEY"]}
        for _ in range(5):
            wait = _last + ib.GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            _last = time.time()
            try:
                r = requests.get(url, params=params, timeout=60)
            except requests.RequestException:
                continue
            if r.status_code != 429:
                break
        else:
            return None, None
        if r.status_code != 200:
            print(sym, day, r.status_code, file=sys.stderr)
            return None, None
        js = r.json().get("results") or {}
        p.write_bytes(gzip.compress(json.dumps(js).encode()))
    sh = js.get("weighted_shares_outstanding") or js.get(
        "share_class_shares_outstanding"
    )
    return sh, js.get("market_cap")


_bars: dict[str, pd.DataFrame] = {}


def cached_day(sym: str, day) -> pd.DataFrame:
    """Regular-session minute bars for one day: intraday_backtest.py's cache, else fetched."""
    if sym not in _bars:
        res = [
            x
            for f in sorted(ib.CACHE.glob(f"{sym}_*.json.gz"))
            for x in json.loads(gzip.decompress(f.read_bytes()))
        ]
        if res:
            df = pd.DataFrame(res).drop_duplicates("t")
            df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(ib.ET)
            df = df.set_index("ts").sort_index().between_time("09:30", "15:59")
        else:
            df = pd.DataFrame(columns=["o", "c"], index=pd.DatetimeIndex([], tz=ib.ET))
        _bars[sym] = df
    b = _bars[sym]
    got = b[b.index.date == day]
    if got.empty:
        got = ib.bars_for(sym, [day]).get(day)
        if got is None:
            return b.iloc[0:0]
        got = got.drop(columns=["day"])
        _bars[sym] = got if b.empty else pd.concat([b, got]).sort_index()
    return got


def price_before(sym: str, t: pd.Timestamp) -> float:
    """Last minute close before t (NaN if t is unknown or at the open)."""
    if pd.isna(t):
        return np.nan
    bars = cached_day(sym, t.date())
    before = bars[bars.index < t]
    return before["c"].iloc[-1] if len(before) else np.nan


def main() -> None:
    bt = pd.read_csv(ib.OUT / "intraday_backtest.csv")
    bt = bt[bt["minute_bars"]]
    c = pd.read_csv(ib.OUT / "cases.csv", dtype=str).fillna("")
    c = c[c["event_key"].isin(bt["event_key"]) & (c["during_market_hours"] == "yes")]
    c = c[~c["outcome"].isin(["settled", "withdrawn"])]
    c = c[c["outcome_for_company"].isin(["good", "bad"])]
    fwd = c["notes"].str.startswith("final written decision")
    c = c[(c["category"] != "ptab") | fwd].copy()
    c["t0"] = pd.to_datetime(c["first_public_time_et"].str[:16], errors="coerce")
    c["t0"] = c["t0"].dt.tz_localize(ib.ET)
    first_day = c.groupby("ticker")["decision_date"].min()
    caps = []
    for _, r in c.iterrows():
        sh, mc = shares(r["ticker"], first_day[r["ticker"]])
        p = price_before(r["ticker"], r["t0"])
        caps.append(sh * p if sh and not np.isnan(p) else mc)
    c["cap_on_day"] = caps
    c = c[c["cap_on_day"].notna() & (c["cap_on_day"] < CAP_MAX)]
    c = c.sort_values("cap_on_day").drop_duplicates("case_id")

    keep = []
    for key, g in c.groupby("event_key"):
        r = bt[bt["event_key"] == key].iloc[0].to_dict()
        good = (g["outcome_for_company"] == "good").sum()
        bad = (g["outcome_for_company"] == "bad").sum()
        r["direction"] = 1 if good > bad else -1 if bad > good else 0
        if not r["direction"]:
            continue
        day = pd.to_datetime(r["decision_date"]).date()
        stock, bench = cached_day(r["ticker"], day), cached_day(r["benchmark"], day)
        t0 = g["t0"].min()
        r["posted_et"] = t0.strftime("%Y-%m-%d %H:%M")
        r["price_before"] = price_before(r["ticker"], t0)
        r["move_post_to_close"] = r["close"] / r["price_before"] - 1
        sb, bb = stock[stock.index < t0], bench[bench.index < t0]
        r["pre_move"] = (
            (sb["c"].iloc[-1] / stock["o"].iloc[0])
            - (bb["c"].iloc[-1] / bench["o"].iloc[0])
            if len(sb) and len(bb)
            else 0.0
        )
        r["cap_on_day"] = g["cap_on_day"].min()
        r["company_role"] = g["company_role"].iloc[0]
        r["party_names"] = "; ".join(
            g["notes"].str.extract(r"party in case: ([^;]+)")[0].dropna()
        )
        r["case_ids"] = "; ".join(g["case_id"])
        r["outcome"] = "; ".join(g["outcome"])
        for d in ib.DELAYS:
            sr = ib.window_ret(stock, t0, d)
            br = ib.window_ret(bench, t0, d)
            a = None if sr is None or br is None else sr - br
            r[f"ret_plus{d}"], r[f"abn_plus{d}"] = sr, a
            r[f"trade_plus{d}"] = None if a is None else r["direction"] * a
        r["excluded_pre_move"] = abs(r["pre_move"]) >= PRE_MOVE_MAX
        keep.append(r)
    out = pd.DataFrame(keep)
    out.to_csv(ib.OUT / "intraday_strict.csv", index=False)
    s = out[~out["excluded_pre_move"]]
    print(
        f"{len(out)} events after type/size/one-side filters; {len(s)} after pre-move filter"
    )
    for d in ib.DELAYS:
        x = s[f"trade_plus{d}"].dropna()
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan
        print(
            f"+{d:>2} min: n={len(x)} mean={x.mean():+.4f} median={x.median():+.4f} "
            f"hit={(x > 0).mean():.2f} t={t:+.2f} after5bp={x.mean() - 0.001:+.4f}"
        )


if __name__ == "__main__":
    main()
