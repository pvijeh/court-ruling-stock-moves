"""Download daily bars for LQDA and UTHR stock and listed option contracts.

Free sources only:
- Yahoo Finance chart API, daily bars, one request per option contract.
  Contract symbol: TICKER + YYMMDD + C/P + strike*1000 as 8 digits.
- OCC daily volume report (contracts traded per day, calls and puts).

Yahoo has no endpoint we can use without a login cookie to list strikes, so we
try every strike on a grid and keep the ones that answer with bars. Expired
contracts (the Sept 25 and Oct 2 weeklies) are no longer served.

Writes stock_daily.csv, option_daily.csv and occ_volume.csv next to this file.
"""

from __future__ import annotations

import concurrent.futures as cf
import csv
import hashlib
import io
import json
import os
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / "work" / "lawsuit" / "cache"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
UA = {"User-Agent": f"Mozilla/5.0 (research; {CONTACT})"}
CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range={rng}"
)
OCC = (
    "https://marketdata.theocc.com/volume-query?reportDate={d}&format=csv"
    "&volumeQueryType=O&symbolType=U&symbol={t}&reportType=D&accountType=ALL"
    "&productKind=ALL&porc=BOTH"
)
KEEP_FROM = date(2026, 7, 1)

EXPIRIES = {
    "LQDA": [
        "261009",
        "261016",
        "261023",
        "261030",
        "261106",
        "261120",
        "261218",
        "270115",
        "270319",
        "270416",
    ],
    "UTHR": [
        "261009",
        "261016",
        "261023",
        "261030",
        "261120",
        "261218",
        "270115",
        "270219",
        "270319",
        "270521",
        "270618",
    ],
}


def strike_grid(ticker: str) -> list[float]:
    if ticker == "LQDA":
        return [x / 2 for x in range(2, 321)]  # 1.0 to 160.0 every 0.5
    return [float(x) for x in range(150, 951, 5)]


def cached_get(url: str) -> tuple[int, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if key.exists():
        status, _, body = key.read_text().partition("\n")
        return int(status), body
    for i in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=30)
        except requests.RequestException:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (i + 1))
            continue
        key.write_text(f"{r.status_code}\n{r.text}")
        return r.status_code, r.text
    return 0, ""


def bars(sym: str, rng: str = "6mo") -> list[dict]:
    status, body = cached_get(CHART.format(sym=sym, rng=rng))
    if status != 200:
        return []
    res = json.loads(body)["chart"]["result"]
    if not res or not res[0].get("timestamp"):
        return []
    r = res[0]
    q = r["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(r["timestamp"]):
        day = datetime.fromtimestamp(ts + r["meta"]["gmtoffset"], UTC).date()
        if day < KEEP_FROM or q["close"][i] is None:
            continue
        out.append(
            {
                "date": day.isoformat(),
                "open": q["open"][i],
                "high": q["high"][i],
                "low": q["low"][i],
                "close": q["close"][i],
                "volume": q["volume"][i] or 0,
            }
        )
    return out


def opt_symbol(ticker: str, exp: str, kind: str, strike: float) -> str:
    return f"{ticker}{exp}{kind}{round(strike * 1000):08d}"


def fetch_options() -> list[dict]:
    jobs = [
        (t, e, k, s)
        for t, exps in EXPIRIES.items()
        for e in exps
        for k in "CP"
        for s in strike_grid(t)
    ]

    def one(job):
        t, e, k, s = job
        sym = opt_symbol(t, e, k, s)
        return [
            {
                "ticker": t,
                "expiry": "20" + e,
                "type": k,
                "strike": s,
                "symbol": sym,
                **b,
            }
            for b in bars(sym)
        ]

    rows: list[dict] = []
    with cf.ThreadPoolExecutor(8) as ex:
        for i, got in enumerate(ex.map(one, jobs)):
            rows.extend(got)
            if i % 1000 == 0:
                print(f"{i}/{len(jobs)} contracts tried, {len(rows)} bars", flush=True)
    return rows


def fetch_occ(ticker: str, start: date, end: date) -> list[dict]:
    """Contracts traded per day. OCC counts each trade once per side
    (buyer and seller), so we halve the summed quantity."""
    rows = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            status, body = cached_get(OCC.format(d=d.strftime("%Y%m%d"), t=ticker))
            calls = puts = 0
            if status == 200 and body.strip():
                for rec in csv.DictReader(io.StringIO(body)):
                    qty = int(rec["quantity"] or 0)
                    if rec["porc"] == "C":
                        calls += qty
                    elif rec["porc"] == "P":
                        puts += qty
            if calls or puts:
                rows.append(
                    {
                        "ticker": ticker,
                        "date": d.isoformat(),
                        "call_contracts": calls // 2,
                        "put_contracts": puts // 2,
                    }
                )
        d += timedelta(days=1)
    return rows


def write(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise SystemExit(f"no rows for {path.name}; kept the old file, rerun later")
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {path.name}")


def main() -> None:
    stock = [{"ticker": t, **b} for t in EXPIRIES for b in bars(t, "1y")]
    write(HERE / "stock_daily.csv", stock)
    occ = [
        r for t in EXPIRIES for r in fetch_occ(t, date(2026, 8, 3), date(2026, 10, 9))
    ]
    write(HERE / "occ_volume.csv", occ)
    write(HERE / "option_daily.csv", fetch_options())


if __name__ == "__main__":
    main()
