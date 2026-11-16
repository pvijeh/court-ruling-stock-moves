"""Second strict rerun: the PR #17 sample with three more filters and cost estimates.

Starts from data/universe/combined/intraday_strict.csv (run intraday_strict.py first, after
ptab_label_audit.py has fixed outcome labels) and adds:

- earnings filter: drop the stock-day if the company released results between the prior
  session's 16:00 close and the event day's close. Sources: SEC 8-K item 2.02 acceptance
  times; for foreign filers, a 6-K in that window that Nasdaq's earnings calendar also
  lists for the event day or the prior trading day.
- pre-move from the prior close: stock minus benchmark from the prior session's close to
  the last minute before posting (catches overnight gaps the 9:30 version missed).
  Drop if 3% or more either way, the same cutoff as before.
- liquidity: 20-session average dollar volume before the event day. Main cutoff $5M,
  with $0, $1M, $2M and $10M shown.
- trading cost: each stock-day's bid-ask spread estimated from its own minute bars (Abdi and
  Ranaldo 2017 close/high/low estimator), charged once per round trip (half each way).
- market sensitivity: a 60-session beta to the benchmark, for a beta-adjusted return.

Needs POLYGON_API_KEY. Caches outside the repo.
Output: data/universe/combined/intraday_strict2.csv and a summary printout.
"""

from __future__ import annotations

import gzip
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import intraday_backtest as ib
import intraday_strict as st

CACHE = Path.home() / "work" / "altdata" / "cache"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
WEB_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0"
# tickers SEC's current ticker file no longer lists
OLD_CIK = {"COMM": 1517228}  # CommScope, renamed Vistance Networks (VISN) in Jan 2026
PRE_MOVE_MAX = 0.03
ADV_MAIN = 5e6
ADV_LEVELS = (0, 1e6, 2e6, 5e6, 1e7)
DELAY = 1


def cached_get(kind: str, key: str, url: str, headers: dict, pause: float) -> dict:
    p = CACHE / kind / f"{key}.json.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return json.loads(gzip.decompress(p.read_bytes()))
    for i in range(4):
        time.sleep(pause)
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 200:
            p.write_bytes(gzip.compress(r.content))
            return r.json()
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url.split('?')[0]} -> {r.status_code}")


def daily(sym: str, day: date) -> pd.DataFrame:
    start, end = day - timedelta(days=130), day
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{sym.replace('-', '.')}/range/1/day/"
        f"{start}/{end}?adjusted=true&sort=asc&limit=500&apiKey={os.environ['POLYGON_API_KEY']}"
    )
    js = cached_get("polygon_day", f"{sym}_{start}_{end}", url, {}, ib.GAP)
    df = pd.DataFrame(js.get("results") or [])
    df["day"] = (
        pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(ib.ET).dt.date
    )
    return df.set_index("day")


def ciks() -> dict[str, int]:
    js = cached_get(
        "sec",
        "company_tickers",
        "https://www.sec.gov/files/company_tickers.json",
        {"User-Agent": SEC_UA},
        0.2,
    )
    m = {v["ticker"]: v["cik_str"] for v in js.values()}
    return {**m, **OLD_CIK}


def filings(cik: int) -> pd.DataFrame:
    js = cached_get(
        "sec",
        f"sub_{cik}",
        f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
        {"User-Agent": SEC_UA},
        0.2,
    )
    df = pd.DataFrame(js["filings"]["recent"])
    df["accepted"] = pd.to_datetime(df["acceptanceDateTime"], utc=True).dt.tz_convert(
        ib.ET
    )
    return df


def nasdaq_reporters(day: date) -> set[str]:
    js = cached_get(
        "nasdaq_earnings",
        str(day),
        f"https://api.nasdaq.com/api/calendar/earnings?date={day}",
        {"User-Agent": WEB_UA, "Accept": "application/json"},
        1.0,
    )
    return {r["symbol"] for r in (js.get("data") or {}).get("rows") or []}


def earnings(sym: str, cik: int | None, prev: date, day: date) -> str:
    """Why the stock-day counts as an earnings day ('' if it doesn't)."""
    lo = pd.Timestamp(f"{prev} 16:00", tz=ib.ET)
    hi = pd.Timestamp(f"{day} 16:00", tz=ib.ET)
    if cik:
        f = filings(cik)
        w = f[(f["accepted"] > lo) & (f["accepted"] <= hi)]
        k = w[(w["form"] == "8-K") & w["items"].str.contains("2.02")]
        if len(k):
            return f"8-K item 2.02 accepted {k['accepted'].iloc[0]:%Y-%m-%d %H:%M} ET"
        six = w[w["form"] == "6-K"]
        if len(six) and (sym in nasdaq_reporters(day) or sym in nasdaq_reporters(prev)):
            return f"6-K accepted {six['accepted'].iloc[0]:%Y-%m-%d %H:%M} ET, on Nasdaq earnings calendar"
    if sym in nasdaq_reporters(day):
        return "on Nasdaq earnings calendar for the event day"
    return ""


def spread_ar(bars: pd.DataFrame) -> float:
    """Abdi-Ranaldo (2017) spread estimate from consecutive minute bars."""
    c, eta = (
        np.log(bars["c"].to_numpy()),
        (np.log(bars["h"]) + np.log(bars["l"])).to_numpy() / 2,
    )
    if len(c) < 30:
        return np.nan
    s2 = 4 * np.mean((c[:-1] - eta[:-1]) * (c[:-1] - eta[1:]))
    return float(np.sqrt(max(s2, 0.0)))


def beta(stock: pd.DataFrame, bench: pd.DataFrame, day: date) -> float:
    r = pd.concat([stock["c"], bench["c"]], axis=1, keys=["s", "b"]).dropna()
    r = r[r.index < day].pct_change().dropna().tail(60)
    return float(np.cov(r["s"], r["b"])[0, 1] / r["b"].var()) if len(r) >= 40 else 1.0


def stats(x: pd.Series, by: pd.Series | None = None) -> str:
    x = x.dropna()
    if by is not None:
        x = x.groupby(by.loc[x.index]).mean()
    if len(x) < 2:
        return f"n={len(x)}"
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return (
        f"n={len(x)} mean={x.mean():+.2%} median={x.median():+.2%} "
        f"up={(x > 0).mean():.0%} t={t:+.2f}"
    )


def main() -> None:
    s = pd.read_csv(ib.OUT / "intraday_strict.csv")
    cik = ciks()
    rows = []
    for _, r in s.iterrows():
        r = r.to_dict()
        day = pd.to_datetime(r["decision_date"]).date()
        t0 = pd.Timestamp(r["posted_et"]).tz_localize(ib.ET)
        dd, bd = daily(r["ticker"], day), daily(r["benchmark"], day)
        hist = dd[dd.index < day]
        prev = hist.index[-1]
        stock, bench = (
            st.cached_day(r["ticker"], day),
            st.cached_day(r["benchmark"], day),
        )
        sb, bb = stock[stock.index < t0], bench[bench.index < t0]
        s_last = sb["c"].iloc[-1] if len(sb) else stock["o"].iloc[0]
        b_last = bb["c"].iloc[-1] if len(bb) else bench["o"].iloc[0]
        r["prior_close"] = hist["c"].iloc[-1]
        r["pre_move_prior_close"] = (s_last / hist["c"].iloc[-1]) - (
            b_last / bd.loc[prev, "c"]
        )
        last20 = hist.tail(20)
        r["adv20_usd"] = float((last20["v"] * last20["vw"]).mean())
        r["earnings"] = earnings(r["ticker"], cik.get(r["ticker"]), prev, day)
        r["spread_est"] = spread_ar(stock)
        r["beta"] = beta(dd, bd, day)
        sr, br = ib.window_ret(stock, t0, DELAY), ib.window_ret(bench, t0, DELAY)
        r["trade"] = r[f"trade_plus{DELAY}"]
        r["trade_beta"] = (
            None if sr is None or br is None else r["direction"] * (sr - r["beta"] * br)
        )
        r["trade_net"] = None if pd.isna(r["trade"]) else r["trade"] - r["spread_est"]
        r["drop_pre_move"] = abs(r["pre_move_prior_close"]) >= PRE_MOVE_MAX
        r["drop_earnings"] = bool(r["earnings"])
        rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(ib.OUT / "intraday_strict2.csv", index=False)

    base = out[out["trade"].notna()]
    print(
        f"{len(out)} stock-days from intraday_strict.csv, {len(base)} with a +{DELAY} min trade"
    )
    print(
        f"  dropped for earnings: {base['drop_earnings'].sum()}; "
        f"for pre-move from prior close: {base['drop_pre_move'].sum()}"
    )
    clean = base[~base["drop_earnings"] & ~base["drop_pre_move"]]
    for lvl in ADV_LEVELS:
        g = clean[clean["adv20_usd"] >= lvl]
        tag = " (main)" if lvl == ADV_MAIN else ""
        print(f"ADV >= ${lvl / 1e6:.0f}M{tag}")
        print("  gross        ", stats(g["trade"]))
        print("  beta-adjusted", stats(g["trade_beta"]))
        print("  after spread ", stats(g["trade_net"]))
        print("  per stock    ", stats(g["trade"], g["ticker"]))
        print(f"  median spread est {g['spread_est'].median():.2%}")


if __name__ == "__main__":
    main()
