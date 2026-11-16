"""HTTP helpers for scripts/universe_deal_litigation.py (copied from common.py).

Every response is cached under data/universe/deal_litigation/raw/ so a rerun
makes no new requests. Keys go in headers only, never in cache file names.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "deal_litigation"
RAW = OUT / "raw"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
WEB_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
# courtlistener: account cap is about 5/minute and shared with other sessions
_MIN_GAP = {
    "sec.gov": 0.15,
    "courts.delaware.gov": 1.0,
    "courtlistener.com": 13.0,
    "yahoo.com": 0.5,
    "polygon.io": 12.5,
    "news.google.com": 1.5,
}
_last: dict[str, float] = {}


def _throttle(host: str) -> None:
    for key, gap in _MIN_GAP.items():
        if host.endswith(key):
            wait = _last.get(key, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[key] = time.time()


def cache_path(url: str, sub: str) -> Path:
    clean = re.sub(r"apiKey=[^&]+", "", url)
    digest = hashlib.sha1(clean.encode()).hexdigest()[:12]
    name = re.sub(r"[^A-Za-z0-9]+", "_", clean)[-120:] + "_" + digest
    return RAW / sub / name


def get(
    url: str,
    sub: str = "misc",
    binary: bool = False,
    tries: int = 3,
    offline: bool = False,
) -> str | bytes:
    """GET with an on-disk cache; '' (or b'') on failure."""
    path = cache_path(url, sub)
    if path.exists():
        return path.read_bytes() if binary else path.read_text()
    if offline:
        return b"" if binary else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    host = urllib.parse.urlparse(url).hostname or ""
    headers = {"User-Agent": SEC_UA if host.endswith("sec.gov") else WEB_UA}
    if host.endswith("yahoo.com"):
        headers["User-Agent"] = (
            "Mozilla/5.0"  # Yahoo returns 429 to full browser strings
        )
    if host.endswith("courtlistener.com") and os.environ.get("COURTLISTENER_API_TOKEN"):
        headers["Authorization"] = "Token " + os.environ["COURTLISTENER_API_TOKEN"]
    real = url
    if host.endswith("polygon.io"):
        sep = "&" if "?" in url else "?"
        real = url + sep + "apiKey=" + os.environ.get("POLYGON_API_KEY", "")
    for i in range(tries):
        _throttle(host)
        try:
            r = requests.get(real, headers=headers, timeout=60)
        except requests.RequestException:
            time.sleep(3 * (i + 1))
            continue
        if r.status_code == 200:
            if binary:
                path.write_bytes(r.content)
                return r.content
            path.write_text(r.text)
            return r.text
        if r.status_code in (202, 429, 500, 502, 503):
            if host.endswith("courtlistener.com") and r.status_code == 429:
                return ""
            time.sleep(15 * (i + 1))
            continue
        break
    return b"" if binary else ""


def get_json(url: str, sub: str = "misc", offline: bool = False) -> dict:
    t = get(url, sub, offline=offline)
    try:
        return json.loads(t) if t else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- Delaware opinions
DEL = "https://courts.delaware.gov"
DEL_COURTS = ("Court of Chancery", "Supreme Court")
FIRST_YEAR = 2021


def _del_rows(page_html: str) -> list[dict]:
    import html as _html

    out = []
    for r in re.findall(r"<tr.*?</tr>", page_html, re.DOTALL)[1:]:
        cells = [
            re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<td.*?</td>", r, re.DOTALL)
        ]
        ids = re.findall(r"download\.aspx\?id=(\d+)", r)
        if len(cells) < 6:
            continue
        out.append(
            {
                "cells": cells,
                "id": ids[0] if ids else "",
            }
        )
    return out


def delaware_opinions(offline: bool = False) -> list[dict]:
    """Every Chancery and Supreme Court opinion/order on the public list since 2021."""
    import datetime as _dt

    rows = []
    for court in DEL_COURTS:
        for year in range(FIRST_YEAR, _dt.date.today().year + 1):
            page, pages = 1, 1
            while page <= pages:
                q = urllib.parse.urlencode(
                    {
                        "ag": court,
                        "typ": "",
                        "div": "",
                        "period": "year",
                        "year": str(year),
                        "results": "100",
                        "ss": "",
                        "srt": "",
                        "srtord": "",
                        "page": str(page),
                    }
                )
                t = get(f"{DEL}/opinions/index.aspx?{q}", "delaware", offline=offline)
                m = re.findall(r'aria-label="Page \d+ of (\d+)"', t)
                pages = int(m[0]) if m else 1
                for r in _del_rows(t):
                    r["court_list"] = court
                    r["year"] = year
                    rows.append(r)
                page += 1
    return rows


def opinion(op_id: str, offline: bool = False) -> dict:
    """Text and PDF timestamps of one Delaware opinion (PDF itself not kept)."""
    import io

    from pypdf import PdfReader

    path = RAW / "opinions" / f"{op_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    if offline:
        return {}
    pdf = get(f"{DEL}/opinions/download.aspx?id={op_id}", "pdf_tmp", binary=True)
    tmp = cache_path(f"{DEL}/opinions/download.aspx?id={op_id}", "pdf_tmp")
    if tmp.exists():
        tmp.unlink()
    out: dict = {"id": op_id, "text": "", "meta": {}}
    try:
        reader = PdfReader(io.BytesIO(pdf))
        meta = reader.metadata or {}
        out["meta"] = {k: str(v) for k, v in meta.items()}
        out["pages"] = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        out["chars"] = len(text)
        # keep the caption/background and the conclusion; that is all we read
        out["text"] = (
            text if len(text) < 40000 else text[:25000] + "\n[...]\n" + text[-12000:]
        )
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)[:200]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


# ---------------------------------------------------------------- market data
import datetime as dt
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
YAHOO = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{s}"
    "?period1=1388534400&period2=1792000000&interval=1d&events=div%2Csplit"
)
_px: dict[str, dict] = {}


_splits: dict[str, list[tuple[dt.date, float]]] = {}


def daily(sym: str, offline: bool = False) -> dict[dt.date, tuple[float, float]]:
    """Yahoo split-adjusted close and volume by date (empty if Yahoo lacks it)."""
    if sym not in _px:
        out: dict[dt.date, tuple[float, float]] = {}
        try:
            res = json.loads(get(YAHOO.format(s=sym), "yahoo", offline=offline))
            res = res["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            for t, c, v in zip(res["timestamp"], q["close"], q["volume"]):
                if c is not None:
                    day = dt.datetime.fromtimestamp(t, ET).date()
                    out[day] = (c, v or 0)
            for e in res.get("events", {}).get("splits", {}).values():
                day = dt.datetime.fromtimestamp(e["date"], ET).date()
                _splits.setdefault(sym, []).append(
                    (day, e["numerator"] / e["denominator"])
                )
        except (ValueError, KeyError, TypeError, IndexError):
            pass
        _px[sym] = out
    return _px[sym]


def split_factor_after(sym: str, d: dt.date) -> float:
    """Shares-per-old-share from splits after d (Yahoo prices are split-adjusted)."""
    daily(sym)
    f = 1.0
    for day, r in _splits.get(sym, []):
        if day > d:
            f *= r
    return f


def trading_day_on_or_after(sym: str, d: dt.date) -> int | None:
    days = sorted(daily(sym))
    for i, x in enumerate(days):
        if x >= d:
            return i
    return None


def ret(sym: str, d: dt.date, span: int = 1) -> float | None:
    """Close-to-close return from the close before d to span trading days later."""
    days = sorted(daily(sym))
    i = trading_day_on_or_after(sym, d)
    if i is None or i == 0 or i + span - 1 >= len(days):
        return None
    px = daily(sym)
    return px[days[i + span - 1]][0] / px[days[i - 1]][0] - 1


def price_on(sym: str, d: dt.date) -> float | None:
    """Last close on or before d."""
    px = daily(sym)
    before = [x for x in px if x <= d]
    return px[max(before)][0] if before else None


def adv_usd(sym: str, d: dt.date, n: int = 20) -> float | None:
    days = sorted(daily(sym))
    i = trading_day_on_or_after(sym, d)
    if i is None or i < n:
        return None
    px = daily(sym)
    return sum(px[x][0] * px[x][1] for x in days[i - n : i]) / n


def companyfacts(cik: str, offline: bool = False) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    return get_json(url, "sec_facts", offline=offline)


REV_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
    "TotalRevenuesAndOtherIncome",
    "InterestAndDividendIncomeOperating",
)


def shares_outstanding(facts: dict, d: dt.date) -> float | None:
    """dei:EntityCommonStockSharesOutstanding from the last filing before d.

    Dual-class companies report one value per class on the same date; sum them.
    """
    vals = (
        facts.get("facts", {})
        .get("dei", {})
        .get("EntityCommonStockSharesOutstanding", {})
        .get("units", {})
        .get("shares", [])
    )
    vals = [v for v in vals if v.get("filed") and v["filed"] <= d.isoformat()]
    if not vals:
        return None
    last = max(v["filed"] for v in vals)
    same = {(v["end"], v["val"]) for v in vals if v["filed"] == last}
    end = max(e for e, _ in same)
    return float(sum(val for e, val in same if e == end))


def revenue_ttm(facts: dict, d: dt.date) -> float | None:
    """Trailing-twelve-month revenue known on d: last fiscal year + latest
    year-to-date period minus the same period a year earlier."""
    ds = d.isoformat()
    gaap = facts.get("facts", {}).get("us-gaap", {}) or facts.get("facts", {}).get(
        "ifrs-full", {}
    )
    best = None
    for tag in REV_TAGS + ("Revenue",):
        units = gaap.get(tag, {}).get("units", {})
        vals = units.get("USD") or next(iter(units.values()), [])
        vals = [v for v in vals if v.get("start") and v["filed"] <= ds]
        if not vals:
            continue

        def length(v: dict) -> int:
            return (
                dt.date.fromisoformat(v["end"]) - dt.date.fromisoformat(v["start"])
            ).days

        annual = [v for v in vals if 350 <= length(v) <= 380]
        if not annual:
            continue
        a = max(annual, key=lambda v: (v["end"], v["filed"]))
        ttm = float(a["val"])
        ytd = [v for v in vals if v["end"] > a["end"] and 80 <= length(v) < 350]
        if ytd:
            y = max(ytd, key=lambda v: (v["end"], length(v)))
            ystart = dt.date.fromisoformat(y["start"]) - dt.timedelta(days=365)
            prior = [
                v
                for v in vals
                if abs((dt.date.fromisoformat(v["start"]) - ystart).days) < 8
                and abs(length(v) - length(y)) < 8
            ]
            if prior:
                ttm = ttm + float(y["val"]) - float(prior[0]["val"])
        end = a["end"] if not ytd else max(a["end"], y["end"])
        if best is None or end > best[0]:
            best = (end, ttm)
    return best[1] if best else None


def sec_filings(cik: str, offline: bool = False) -> list[dict]:
    """Every filing (form, date, accession, acceptance time) from EDGAR submissions."""
    base = "https://data.sec.gov/submissions/"
    js = get_json(f"{base}CIK{int(cik):010d}.json", "sec_sub", offline=offline)
    blocks = [js.get("filings", {}).get("recent", {})]
    for f in js.get("filings", {}).get("files", []):
        blocks.append(get_json(base + f["name"], "sec_sub", offline=offline))
    out = []
    for b in blocks:
        for i, form in enumerate(b.get("form", [])):
            out.append(
                {
                    "form": form,
                    "date": b["filingDate"][i],
                    "adsh": b["accessionNumber"][i],
                    "accepted": b["acceptanceDateTime"][i],
                    "items": b.get("items", [""] * (i + 1))[i],
                    "doc": b["primaryDocument"][i],
                }
            )
    return out


def efts(
    q: str, cik: str, start: dt.date, end: dt.date, forms: str, offline: bool = False
) -> list[dict]:
    """EDGAR full-text search hits for q in one company's filings."""
    url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(
        {
            "q": q,
            "ciks": f"{int(cik):010d}",
            "forms": forms,
            "dateRange": "custom",
            "startdt": start.isoformat(),
            "enddt": end.isoformat(),
        }
    )
    js = get_json(url, "sec_efts", offline=offline)
    return [
        h["_source"] | {"_id": h["_id"]} for h in js.get("hits", {}).get("hits", [])
    ]


def acceptance(cik: str, adsh: str, offline: bool = False) -> dt.datetime | None:
    """EDGAR 'Accepted' time (ET) from the public filing index page."""
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{adsh.replace('-', '')}/{adsh}-index.htm"
    )
    t = get(url, "sec_index", offline=offline)
    m = re.search(r"Accepted</div>\s*<div class=\"info\">([\d\- :]+)</div>", t)
    if not m:
        return None
    return dt.datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=ET
    )


def minute_bars(sym: str, day: dt.date) -> list[tuple[dt.datetime, float]]:
    """Polygon 1-minute bars for one day (free plan covers about 2 years)."""
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/{day}/{day}"
        "?adjusted=true&sort=asc&limit=50000"
    )
    js = get_json(url, "polygon")
    return [
        (dt.datetime.fromtimestamp(b["t"] / 1000, ET), b["c"])
        for b in js.get("results") or []
    ]


def minutes_to_half(sym: str, t0: dt.datetime) -> float | None:
    """Minutes after t0 until the price first covered half of its t0-to-close move."""
    bars = [
        (t, c)
        for t, c in minute_bars(sym, t0.date())
        if dt.time(9, 30) <= t.time() < dt.time(16, 0)
    ]
    before = [c for t, c in bars if t <= t0]
    after = [(t, c) for t, c in bars if t > t0]
    if not before or not after:
        return None
    p0, close = before[-1], after[-1][1]
    half = p0 + (close - p0) / 2
    for t, c in after:
        if (close >= p0 and c >= half) or (close < p0 and c <= half):
            return round((t - t0).total_seconds() / 60)
    return None


# ---------------------------------------------------------------- case table
COLUMNS = [
    "case_id",
    "case_type",
    "case_name",
    "court",
    "docket_number",
    "docket_url",
    "ticker",
    "company",
    "company_role",
    "counterparty",
    "counterparty_ticker",
    "filed_date",
    "trial_start_date",
    "trial_end_date",
    "decision_date",
    "decision_time_et",
    "decision_known_in_advance",
    "decision_source_url",
    "outcome",
    "outcome_for_company",
    "days_filed_to_decision",
    "market_cap_usd_at_filing",
    "revenue_ttm_usd_at_filing",
    "revenue_at_stake_usd",
    "revenue_at_stake_share",
    "ret_filing_day",
    "abn_ret_filing_day",
    "ret_decision_day",
    "abn_ret_decision_day",
    "ret_decision_plus5",
    "adv_usd_20d_before_decision",
    "implied_move_before_decision",
    "settlement_amount_usd",
    "confidence",
    "sources",
    "notes",
    "first_public_source",
    "first_public_time_et",
    "time_precision",
    "during_market_hours",
    "company_release_time_et",
    "lead_minutes_vs_company_release",
    "minutes_to_half_move",
    "minute_data_available",
]
FIELDS = [
    "case_id",
    "case_type",
    "case_name",
    "court",
    "docket",
    "parties",
    "counterparty",
    "filed",
    "trial_start",
    "trial_end",
    "decision_date",
    "op_id",
    "known",
    "outcome",
    "settlement",
    "conf",
    "notes",
]
# drug makers and biotechs are measured against XBI, everything else against SPY
XBI_NAMES = {"AZN", "BMY", "JNJ", "BBIO", "AXSM", "VXRT", "GILD", "NVS", "TAK", "PCRX"}
TODAY = dt.date.today()
POLYGON_START = TODAY - dt.timedelta(days=730)


def curated() -> list[dict]:
    rows = []
    for line in CURATED.strip().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        vals = line.split("|")
        assert len(vals) == len(FIELDS), (len(vals), line[:60])
        rows.append(dict(zip(FIELDS, (v.strip() for v in vals))))
    return rows


def _date(s: str) -> dt.date | None:
    return dt.date.fromisoformat(s) if s else None


def _pdf_time(op: dict, day: dt.date) -> dt.datetime | None:
    """PDF last-saved time, used only when it falls on the decision date."""
    raw = op.get("meta", {}).get("/ModDate", "")
    m = re.match(r"D:(\d{12})", raw)
    if not m:
        return None
    t = dt.datetime.strptime(m.group(1), "%Y%m%d%H%M").replace(tzinfo=ET)
    if "Z" in raw[16:18] or raw[16:17] == "+":  # UTC or a non-US offset
        return None
    return t if t.date() == day else None


def market_open(t: dt.datetime, sym: str) -> bool:
    return t.date() in daily("SPY") and dt.time(9, 30) <= t.time() < dt.time(16, 0)


def company_release(
    cik: str, day: dt.date, offline: bool = False
) -> tuple[dt.datetime | None, str]:
    """Earliest 8-K/6-K mentioning a court, accepted on day..day+3."""
    hits = efts('"court"', cik, day, day + dt.timedelta(days=3), "8-K,6-K", offline)
    best = None
    for h in hits:
        adsh = h["_id"].split(":")[0]
        t = acceptance(cik, adsh, offline)
        if t and t.date() >= day and (best is None or t < best[0]):
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{adsh.replace('-', '')}/{adsh}-index.htm"
            )
            best = (t, url)
    return best if best else (None, "")


def fmt(x: float | None, nd: int = 4) -> str:
    return "" if x is None else str(round(x, nd))


def build(offline: bool = False) -> list[dict]:
    out = []
    for c in curated():
        parties = [p.split("=") for p in c["parties"].split(";") if p]
        tickers = [p[0] for p in parties]
        filed, dday = _date(c["filed"]), _date(c["decision_date"])
        op = opinion(c["op_id"], offline=offline) if c["op_id"] else {}
        src_url = f"{DEL}/opinions/download.aspx?id={c['op_id']}" if c["op_id"] else ""
        t_pub = _pdf_time(op, dday) if op and dday else None
        for tick, company, role, ofc, cik in parties:
            notes = [c["notes"]]
            bench = "XBI" if tick in XBI_NAMES else "SPY"
            r = {k: "" for k in COLUMNS}
            others = [t for t in tickers if t != tick]
            r.update(
                case_id=c["case_id"],
                case_type=c["case_type"],
                case_name=c["case_name"],
                court=c["court"],
                docket_number=c["docket"],
                docket_url=src_url,
                ticker=tick,
                company=company,
                company_role=role,
                counterparty=c["counterparty"],
                counterparty_ticker=";".join(others),
                filed_date=c["filed"],
                trial_start_date=c["trial_start"],
                trial_end_date=c["trial_end"],
                decision_date=c["decision_date"],
                decision_known_in_advance=c["known"],
                decision_source_url=src_url,
                outcome=c["outcome"],
                outcome_for_company=ofc,
                settlement_amount_usd=c["settlement"],
                confidence=c["conf"],
                minute_data_available="no",
            )
            if not daily(tick, offline=offline):
                notes.append(
                    f"No Yahoo price history for {tick} (delisted); returns blank."
                )
            if filed and dday:
                r["days_filed_to_decision"] = str((dday - filed).days)
            if filed and cik:
                facts = companyfacts(cik, offline=offline)
                sh, px = shares_outstanding(facts, filed), price_on(tick, filed)
                if sh and px:
                    mcap = sh * px * split_factor_after(tick, filed)
                    r["market_cap_usd_at_filing"] = str(round(mcap))
                rev = revenue_ttm(facts, filed)
                if rev:
                    r["revenue_ttm_usd_at_filing"] = str(round(rev))
            if filed:
                a, b = ret(tick, filed, 2), ret(bench, filed, 2)
                r["ret_filing_day"] = fmt(a)
                r["abn_ret_filing_day"] = fmt(
                    a - b if a is not None and b is not None else None
                )
            if dday:
                if t_pub:
                    r["decision_time_et"] = t_pub.strftime("%H:%M")
                    after = t_pub.time() >= dt.time(16, 0)
                    d0 = dday + dt.timedelta(days=1) if after else dday
                    span = 1
                else:
                    d0, span = dday, 2
                    notes.append(
                        "Decision time unknown: decision-day returns span 2 trading days."
                    )
                a, b = ret(tick, d0, span), ret(bench, d0, span)
                r["ret_decision_day"] = fmt(a)
                r["abn_ret_decision_day"] = fmt(
                    a - b if a is not None and b is not None else None
                )
                r["ret_decision_plus5"] = fmt(ret(tick, d0, 5))
                adv = adv_usd(tick, d0)
                r["adv_usd_20d_before_decision"] = str(round(adv)) if adv else ""
                if c["op_id"]:
                    r["first_public_source"] = (
                        "Delaware Courts opinions page (courts.delaware.gov)"
                    )
                if t_pub:
                    r["first_public_time_et"] = t_pub.strftime("%Y-%m-%d %H:%M")
                    r["time_precision"] = "hour"
                    r["during_market_hours"] = (
                        "yes" if market_open(t_pub, tick) else "no"
                    )
                    notes.append(
                        "Time is the opinion PDF's last-saved stamp (estimate; posting follows)."
                    )
                else:
                    r["first_public_time_et"] = c["decision_date"]
                    r["time_precision"] = "day"
                    r["during_market_hours"] = "unknown"
                if cik:
                    rel, rel_url = company_release(cik, dday, offline)
                    if rel:
                        r["company_release_time_et"] = rel.strftime("%Y-%m-%d %H:%M")
                        r["sources"] = "; ".join(
                            x for x in (r["sources"], rel_url) if x
                        )
                        if t_pub:
                            lead = (rel - t_pub).total_seconds() / 60
                            r["lead_minutes_vs_company_release"] = str(round(lead))
                if (
                    dday >= POLYGON_START
                    and t_pub
                    and r["during_market_hours"] == "yes"
                ):
                    if minute_bars(tick, dday):
                        r["minute_data_available"] = "yes"
                        m = minutes_to_half(tick, t_pub)
                        r["minutes_to_half_move"] = "" if m is None else str(m)
                elif dday >= POLYGON_START and minute_bars(tick, d0):
                    r["minute_data_available"] = "yes"
            r["sources"] = " ; ".join(x for x in (src_url, r["sources"]) if x)
            r["notes"] = " ".join(n for n in notes if n)
            out.append(r)
    return out


def write_csv(rows: list[dict]) -> None:
    import csv

    path = OUT / "cases.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {path}")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cached files only")
    args = ap.parse_args()
    write_csv(build(offline=args.offline))


# Hand-curated cases; every row was checked against the opinion it cites.
# Fields: see FIELDS. parties = TICKER=Company=role=outcome_for_company=CIK;...
CURATED = """
# case_id|case_type|case_name|court|docket|parties(TICK=Company=role=ofc=cik;...)|counterparty|filed|trial_start|trial_end|decision_date|op_id|known|outcome|settlement|conf|notes
williams-et|merger-agreement damages|The Williams Companies, Inc. v. Energy Transfer LP|Del. Ch.|C.A. No. 12168-VCG|WMB=The Williams Companies=plaintiff=good=107263;ET=Energy Transfer LP=defendant=bad=1276187|Energy Transfer / Williams|2016-04-06|2021-05-10|2021-05-21|2021-12-29|328050|no|win|410000000|medium|Post-trial: Williams wins $410M plus interest and fees for ET's breach of the 2016 merger agreement. Win/loss is from Williams' side.
cigna-anthem-appeal|merger-agreement damages (appeal)|Cigna Corporation v. Anthem, Inc.|Del. Supr.|No. 364, 2020|CI=Cigna=appellant=mixed=1739940;ELV=Anthem (Elevance)=appellee=mixed=1156039|Anthem / Cigna|2020-10-01|||2021-05-03|319820|no|split|0|high|Supreme Court affirmed Chancery: neither side gets the $1.85B break fee (Cigna) or ~$14.7B damages (Anthem).
bardy-hillrom|merger-agreement enforcement|Bardy Diagnostics, Inc. v. Hill-Rom, Inc.|Del. Ch.|C.A. No. 2021-0175-JRS|HRC=Hill-Rom Holdings=defendant=bad=47518|Bardy Diagnostics (private)|2021-02-26|2021-05-24|2021-05-27|2021-07-09|322060|no|loss|375000000|high|Court ordered Hill-Rom to close its $375M purchase of Bardy (specific performance). Hill-Rom loss.
columbia-trp|deal / aiding-and-abetting damages|In re Columbia Pipeline Group, Inc. Merger Litigation|Del. Ch.|Cons. C.A. No. 2018-0484-JTL|TRP=TC Energy=defendant=bad=1232384|Former Columbia Pipeline stockholders|2018-06-29|2022-12-05|2022-12-19|2023-06-30|349400|no|loss||medium|Post-trial: TC Energy (TransCanada) liable for aiding and abetting; May 15 2024 judgment about $398M plus interest. Earlier: Mar 1 2021 motion to dismiss denied.
columbia-trp-appeal|deal / aiding-and-abetting damages (appeal)|TC Energy Corp. v. Columbia Pipeline stockholders|Del. Supr.|Appeal of C.A. No. 2018-0484|TRP=TC Energy=appellant=good=1232384|Former Columbia Pipeline stockholders|2024-06-14|||2025-06-17|381090|no|win||medium|Supreme Court reversed the aiding-and-abetting judgment against TC Energy.
boardwalk-loews|controlling-holder buyout damages|Bandera Master Fund LP v. Boardwalk Pipeline Partners, LP|Del. Ch.|C.A. No. 2018-0372-JTL|L=Loews Corporation=defendant=bad=60086|Former Boardwalk unitholders|2018-05-25|2021-02-22|2021-03-02|2021-11-12|326390|no|loss|690000000|medium|Post-trial: Loews' general partner owed ~$690M to Boardwalk unitholders for the 2018 call-right buyout.
boardwalk-loews-appeal|controlling-holder buyout damages (appeal)|Boardwalk Pipeline Partners, LP v. Bandera Master Fund LP|Del. Supr.|No. 13, 2022|L=Loews Corporation=appellant=good=60086|Former Boardwalk unitholders|2022-01-10|||2022-12-19|341590|no|win||medium|Supreme Court reversed the ~$690M judgment and remanded.
boeing-deriv|derivative (oversight) damages|In re The Boeing Company Derivative Litigation|Del. Ch.|C.A. No. 2019-0907-MTZ|BA=Boeing=nominal defendant=good=12927|Boeing directors|2019-11-12|||2021-09-07|324120|no|split|237500000|high|Motion to dismiss denied on the 737 MAX safety-oversight claim; settled Nov 2021 for $237.5M paid to Boeing by insurers.
ggp-brookfield|controlling-holder buyout damages|In re GGP, Inc. Stockholder Litigation|Del. Ch.|C.A. No. 2018-0267-JRS|BN=Brookfield (BAM/BN)=defendant=good=1001085|Former GGP stockholders|2018-04-11|||2021-05-25|320460|no|dismissed||high|Claims over Brookfield Property Partners' 2018 $9.25B GGP buyout dismissed. Supreme Court affirmed Jul 19 2022 (3-2).
ggp-brookfield-appeal|controlling-holder buyout damages (appeal)|In re GGP, Inc. Stockholder Litigation|Del. Supr.|No. 228, 2021|BN=Brookfield (BAM/BN)=appellee=good=1001085|Former GGP stockholders|2021-06-01|||2022-07-19|335730|no|win||high|Supreme Court affirmed dismissal 3-2.
bgc-deriv|controlling-holder deal derivative|In re BGC Partners, Inc. Derivative Litigation|Del. Ch.|C.A. No. 2018-0722-LWW|BGC=BGC Partners=nominal defendant=unknown=1094831|Howard Lutnick / Cantor Fitzgerald|2018-10-01|2022-03-01|2022-03-04|2022-08-19|336820|no|loss||high|Challenge to BGC's $875M purchase of Berkeley Point from Cantor; judgment after trial for defendants (plaintiff loss; BGC was nominal defendant). Affirmed Aug 10 2023.
rosson-brookfield-appeal|controlling-holder dilution claim (appeal)|Brookfield Asset Management, Inc. v. Rosson|Del. Supr.|No. 406, 2020|BN=Brookfield (BAM/BN)=appellant=good=1001085|Former TerraForm Power stockholders|2020-11-01|||2021-09-20|324500|no|win||high|Supreme Court overruled Gentile and dismissed stockholders' direct claims over TerraForm Power's 2018 private placement to Brookfield.
kraft-deriv|derivative (insider selling / oversight)|In re Kraft Heinz Company Derivative Litigation|Del. Ch.|C.A. No. 2019-0587-LWW|KHC=Kraft Heinz=nominal defendant=unknown=1637459|3G Capital / Kraft Heinz directors|2019-07-30|||2021-12-15|327650|no|dismissed||high|Claims that 3G sold $1.2B of stock on inside information dismissed with prejudice; affirmed Aug 1 2022.
yatra-ebix|merger-termination damages|Yatra Online, Inc. v. Ebix, Inc.|Del. Ch.|C.A. No. 2020-0444-JRS|YTRA=Yatra Online=plaintiff=bad=1516899;EBIX=Ebix=defendant=good=814549|Ebix / Yatra|2020-06-05|||2021-08-30|323810|no|dismissed||high|Yatra's claims over Ebix walking away from the $338M merger dismissed in full; affirmed Apr 11 2022.
tesla-solarcity|controlling-holder deal derivative|In re Tesla Motors, Inc. Stockholder Litigation|Del. Ch.|C.A. No. 12711-VCS|TSLA=Tesla=nominal defendant=good=1318605|Elon Musk|2016-09-01|2021-07-12|2021-07-23|2022-04-27|332290|no|loss||high|Post-trial: Musk and the board did not breach duties in Tesla's $2.6B SolarCity purchase (plaintiff loss). Affirmed Jun 6 2023.
tesla-solarcity-appeal|controlling-holder deal derivative (appeal)|In re Tesla Motors, Inc. Stockholder Litigation|Del. Supr.|No. 181, 2022|TSLA=Tesla=nominal defendant=good=1318605|Elon Musk|2022-05-01|||2023-06-06|348500|no|loss||high|Supreme Court affirmed judgment for Musk.
carvana-garcia|controlling-holder stock-sale derivative|In re Carvana Co. Stockholders Litigation|Del. Ch.|C.A. No. 2020-0415-KSJM|CVNA=Carvana=nominal defendant=unknown=1690820|Ernest Garcia II|2020-06-05|||2022-06-30|334950|no|split||medium|Motion to dismiss denied on claims that Garcia II profited from Carvana's $600M 2020 direct offering.
nisource-deriv|derivative (oversight) damages|City of Detroit Police and Fire Retirement System v. Hamrock|Del. Ch.|C.A. No. 2021-0370-KSJM|NI=NiSource=nominal defendant=unknown=1111711|NiSource directors|2021-04-28|||2022-06-30|335090|no|dismissed||high|Caremark claims over the Merrimack Valley gas explosions (over $1B of losses) dismissed.
twitter-musk|merger-agreement enforcement|Twitter, Inc. v. Elon R. Musk|Del. Ch.|C.A. No. 2022-0613-KSJM|TWTR=Twitter=plaintiff=good=1418091|Elon Musk / X Holdings (private)|2022-07-12|||2022-10-04||no|settled|44000000000|high|Musk offered on Oct 4 2022 to close at $54.20 a share; court stayed the Oct 17 trial on Oct 6 (order 338820) and the $44B deal closed Oct 27. Key ruling Jul 19 2022: expedited trial granted at a set hearing.
abc-opioid-deriv|derivative (oversight) damages|Lebanon County Employees' Retirement Fund v. Collis|Del. Ch.|C.A. No. 2021-1118-JTL|COR=AmerisourceBergen (Cencora)=nominal defendant=unknown=1140859|AmerisourceBergen directors|2021-12-30|||2022-12-22|341790|no|dismissed||medium|Caremark claims over opioid distribution (about $6.6B opioid settlement) dismissed; Supreme Court reversed Dec 18 2023.
bridgebio-eidos|controlling-holder buyout damages|SMART Local Unions & Councils Pension Fund v. BridgeBio Pharma|Del. Ch.|C.A. No. 2021-1030-PAF|BBIO=BridgeBio Pharma=defendant=good=1743881|Former Eidos stockholders|2021-11-30|||2022-12-29|342080|no|dismissed||medium|Challenge to BridgeBio's 2021 buyout of the Eidos minority dismissed; affirmed Aug 9 2023.
walmart-opioid-deriv|derivative (oversight) damages|Ontario Provincial Council of Carpenters' Pension Trust Fund v. Walton|Del. Ch.|C.A. No. 2021-0827-JTL|WMT=Walmart=nominal defendant=unknown=104169|Walmart directors and officers|2021-09-27|||2023-04-26|346850|no|split||medium|Opioid-oversight claims (Walmart agreed a $3.1B opioid settlement) partly survive: dismissed as to distributor issues, kept on DEA-settlement and pharmacy issues.
mcd-easterbrook|executive-pay clawback|McDonald's Corporation v. Stephen J. Easterbrook|Del. Ch.|C.A. No. 2020-0658-JRS|MCD=McDonald's=plaintiff=good=63908|Former CEO Stephen Easterbrook|2020-08-10|||2021-12-16||no|settled|105000000|medium|Feb 2 2021 motion to dismiss denied (op 316250); Easterbrook agreed in Dec 2021 to return equity worth about $105M.
oracle-netsuite|controlling-holder deal derivative|In re Oracle Corporation Derivative Litigation|Del. Ch.|C.A. No. 2017-0337-SG|ORCL=Oracle=nominal defendant=good=1341439|Larry Ellison and Safra Catz|2017-05-03|2022-07-18|2022-07-27|2023-05-12|347580|no|loss||high|Post-trial: Ellison did not taint Oracle's $9.3B NetSuite purchase; judgment for defendants (plaintiff loss). Affirmed Jan 21 2025.
oracle-netsuite-appeal|controlling-holder deal derivative (appeal)|In re Oracle Corporation Derivative Litigation|Del. Supr.|No. 182, 2024|ORCL=Oracle=nominal defendant=good=1341439|Larry Ellison and Safra Catz|2024-04-01|||2025-01-21|374260|no|loss||medium|Supreme Court affirmed judgment for defendants.
amc-ape|stock-conversion injunction / settlement|In re AMC Entertainment Holdings, Inc. Stockholder Litigation|Del. Ch.|C.A. No. 2023-0215-MTZ|AMC=AMC Entertainment=defendant=good=1411579|AMC common stockholders|2023-02-20|||2023-08-11|351520|no|settled||high|Status-quo order blocked AMC's APE-to-common conversion; Jul 21 2023 the court rejected the first settlement (op 350440); Aug 11 2023 approved the revised settlement, letting the conversion and reverse split go ahead.
viacom-settlement|merger class action settlement|In re Viacom Inc. Stockholders Litigation|Del. Ch.|C.A. No. 2019-0948-SG|PARA=Paramount Global=defendant=unknown=1826011|National Amusements / Shari Redstone|2019-10-25|||2023-08-01|351380|no|settled|122500000|medium|Settlement of claims over the 2019 CBS-Viacom merger approved ($122.5M).
cbs-viacom|merger class action and derivative|In re CBS Corporation Stockholder Class Action and Derivative Litigation|Del. Ch.|C.A. No. 2020-0111-JRS|PARA=ViacomCBS (Paramount)=defendant=unknown=1826011|National Amusements / Shari Redstone|2020-02-14|||2021-01-27|315980|no|split|167500000|medium|Motions to dismiss largely denied; case later settled for $167.5M (2022).
williams-et-appeal|merger-agreement damages (appeal)|Energy Transfer LP v. The Williams Companies, Inc.|Del. Supr.|No. 123, 2022|WMB=The Williams Companies=appellee=good=107263;ET=Energy Transfer LP=appellant=bad=1276187|Energy Transfer / Williams|2022-03-01|||2023-10-10|353940|no|win|410000000|high|Supreme Court affirmed the $410M judgment and fee award for Williams.
abc-opioid-deriv-appeal|derivative (oversight) damages (appeal)|Lebanon County Employees' Retirement Fund v. Collis|Del. Supr.|No. 21, 2023|COR=AmerisourceBergen (Cencora)=nominal defendant=unknown=1140859|AmerisourceBergen directors|2023-01-20|||2023-12-18|357090|no|split||high|Supreme Court reversed the dismissal and sent the opioid-oversight claims back for trial-court proceedings.
tornetta-musk|executive-pay rescission|Tornetta v. Musk|Del. Ch.|C.A. No. 2018-0408-KSJM|TSLA=Tesla=nominal defendant=bad=1318605|Elon Musk and Tesla directors|2018-06-05|2022-11-14|2022-11-18|2024-01-30|359340|no|loss||high|Post-trial: Musk's 2018 pay package (about $56B) rescinded. Tesla is the nominal defendant; the ruling cancels options granted to its CEO, scored bad for Tesla holders because of the CEO-retention risk the market priced. Dec 19 2025 Supreme Court reversed rescission (op 389200).
match-iac-appeal|controlling-holder separation (appeal)|In re Match Group, Inc. Derivative Litigation|Del. Supr.|No. 368, 2022|MTCH=Match Group=defendant=mixed=891103|IAC (former controller)|2022-10-01|||2024-04-04|362250|no|split||medium|Supreme Court affirmed in part and reversed in part: entire fairness applies to all controller deals unless MFW is met; claims over the 2020 IAC-Match separation partly revived.
terraform-brookfield-appeal|controlling-holder buyout damages (appeal)|In re TerraForm Power, Inc. Stockholders Litigation (Brookfield buyout)|Del. Supr.|No. 311, 2023|BN=Brookfield (BAM/BN)=appellee=bad=1001085|Former TerraForm Power stockholders|2023-08-01|||2024-03-25|361770|no|split||medium|Supreme Court reversed the dismissal of claims over Brookfield Renewable's 2020 buyout of TerraForm Power's minority, sending the case back.
amc-ape-appeal|stock-conversion settlement (appeal)|In re AMC Entertainment Holdings, Inc. Stockholder Litigation|Del. Supr.|No. 315, 2023|AMC=AMC Entertainment=appellee=good=1411579|AMC common stockholders|2023-08-20|||2024-05-20|364280|no|win||high|Supreme Court affirmed approval of the AMC settlement.
vt-edwards|earnout damages|VT Shareholder Representative, LLC v. Edwards Lifesciences Corporation|Del. Ch.|C.A. No. 2023-0316-MAA|EW=Edwards Lifesciences=defendant=good=1099800|Former Valtech Cardio holders||||2023-12-12|356770|no|dismissed||medium|Claims for up to $350M of unpaid Valtech milestone payments dismissed (Rule 12(b)(1)); affirmed Jul 31 2024 (op 367320).
vt-edwards-appeal|earnout damages (appeal)|VT Shareholder Representative, LLC v. Edwards Lifesciences Corporation|Del. Supr.|No. 2, 2024|EW=Edwards Lifesciences=appellee=good=1099800|Former Valtech Cardio holders||||2024-07-31|367320|no|win||medium|Supreme Court affirmed dismissal.
fortis-jnj|earnout damages|Fortis Advisors LLC v. Johnson & Johnson|Del. Ch.|C.A. No. 2020-0881-LWW|JNJ=Johnson & Johnson=defendant=bad=200406|Former Auris Health holders|2020-10-15|2023-10-23|2023-11-03|2024-09-04|369060|no|loss|1000000000|medium|Post-trial: J&J breached the Auris earnout; about $1B in damages plus interest.
srs-alexion|earnout damages|Shareholder Representative Services LLC v. Alexion Pharmaceuticals, Inc.|Del. Ch.|C.A. No. 2020-1069-MTZ|AZN=AstraZeneca (Alexion)=defendant=bad=901832|Former Syntimmune holders|2020-12-15|||2024-09-05|369130|no|loss||medium|Post-trial: Alexion breached the Syntimmune merger agreement by dropping the ALXN1830 program; damages set later (Jun 11 2025, op 380920).
boardwalk-loews-remand|controlling-holder buyout damages (remand)|Bandera Master Fund LP v. Boardwalk Pipeline Partners, LP|Del. Ch.|C.A. No. 2018-0372-JTL|L=Loews Corporation=defendant=good=60086|Former Boardwalk unitholders|2018-05-25|||2024-09-09|369200|no|win||high|On remand, judgment for defendants on all remaining claims. Supreme Court later ruled again (Dec 10 2025, op 388670).
arc-dwac|merger conversion-ratio claim|ARC Global Investments II, LLC v. Digital World Acquisition Corp.|Del. Ch.|C.A. No. 2024-0186-LWW|DJT=Trump Media & Technology Group (DWAC)=defendant=good=1849635|ARC Global (SPAC sponsor)|2024-02-29|2024-08-26|2024-08-28|2024-09-16|369380|no|win||medium|Sponsor ARC's claim to millions more TMTG shares under the conversion ratio rejected after trial.
tornetta-musk-ratification|executive-pay rescission (post-trial ratification)|Tornetta v. Musk|Del. Ch.|C.A. No. 2018-0408-KSJM|TSLA=Tesla=nominal defendant=bad=1318605|Elon Musk and Tesla directors|2018-06-05|||2024-12-02|372420|no|loss||high|Court refused to let Tesla's June 2024 stockholder re-vote revive the 2018 pay package; awarded $345M fees.
desktop-nano|merger-agreement enforcement|Desktop Metal, Inc. v. Nano Dimension Ltd.|Del. Ch.|C.A. No. 2024-1303-KSJM|DM=Desktop Metal=plaintiff=good=1754820;NNDM=Nano Dimension=defendant=bad=1643303|Nano Dimension / Desktop Metal|2024-12-27|2025-03-03|2025-03-06|2025-03-24|377240|no|win||high|Post-trial: Nano Dimension ordered to get regulatory (CFIUS) clearance and close its ~$179M purchase of Desktop Metal (specific performance). Order PDF saved 18:09 ET, after the close.
fox-dominion-deriv|derivative (oversight) damages|In re Fox Corporation Derivative Litigation|Del. Ch.|C.A. No. 2023-0418-JTL|FOXA=Fox Corporation=nominal defendant=unknown=1754301|Murdoch family and Fox directors|2023-07-10|||2024-12-27|373470|no|split||medium|Demand-futility motion denied on Count II: claims over Fox's $787.5M Dominion defamation settlement can go forward against the Murdochs.
activision-msft|merger class action damages|Sjunde AP-Fonden v. Activision Blizzard, Inc.|Del. Ch.|C.A. No. 2022-1001-KSJM|MSFT=Microsoft=defendant=bad=789019|Former Activision Blizzard stockholders|2022-12-01|||2025-10-02|385520|no|split||medium|Motions to dismiss claims over Microsoft's $68.7B Activision purchase (including against Microsoft) largely denied; treasury-dividend claims converted to summary judgment. Feb 29 2024 earlier ruling found the merger approval broke DGCL 251 procedure but denied dismissal.
srs-alexion-damages|earnout damages (remedy)|Shareholder Representative Services LLC v. Alexion Pharmaceuticals, Inc.|Del. Ch.|C.A. No. 2020-1069-MTZ|AZN=AstraZeneca (Alexion)=defendant=bad=901832|Former Syntimmune holders|2020-12-15|||2025-06-11|380920|no|loss||medium|Remedy opinion awarding Syntimmune holders damages on the Sept 2024 liability ruling; exact total not extracted (opinion mentions milestone values of $130M to $1.35B). Saved 16:14 ET, after close.
tornetta-musk-appeal|executive-pay rescission (appeal)|In re Tesla, Inc. Derivative Litigation (Tornetta v. Musk)|Del. Supr.|No. 10, 2025|TSLA=Tesla=nominal defendant=good=1318605|Elon Musk and Tesla directors|2025-01-10|||2025-12-19|389200|no|win||high|Supreme Court reversed the rescission of Musk's 2018 pay package and awarded $1 in nominal damages; fee award cut.
boardwalk-loews-appeal2|controlling-holder buyout damages (second appeal)|Bandera Master Fund LP v. Boardwalk Pipeline Partners, LP|Del. Supr.|No. 401, 2024|L=Loews Corporation=appellee=bad=60086|Former Boardwalk unitholders|2024-10-01|||2025-12-10|388670|no|split||medium|Supreme Court reversed the judgment for defendants on the tortious-interference count and remanded; other claims stay resolved for defendants.
fortis-jnj-appeal|earnout damages (appeal)|Johnson & Johnson v. Fortis Advisors LLC|Del. Supr.|No. 434, 2024|JNJ=Johnson & Johnson=appellant=mixed=200406|Former Auris Health holders|2024-10-15|||2026-01-12|389980|no|split|1000000000|medium|Supreme Court affirmed breach of contract and fraud but reversed the implied-covenant ruling, removing the Milestone 1 payment from the damages. Saved 16:01 ET.
dell-classv|controlling-holder stock-exchange class action|In re Dell Technologies Inc. Class V Stockholders Litigation|Del. Ch.|C.A. No. 2018-0816-JTL|DELL=Dell Technologies=defendant=bad=1571996|Former Class V stockholders / Michael Dell and Silver Lake|2018-11-13|||2023-08-21|350730|no|settled|1000000000|medium|Claims over Dell's 2018 exchange of its VMware tracking stock settled for $1B (agreed Nov 2022). Decision date is the court's fee opinion after approving the settlement; date of the settlement-approval hearing not extracted.
charter-liberty|controlling-holder deal derivative|Hollywood Firefighters' Pension Fund v. Malone (Charter / Liberty Broadband)|Del. Ch.|C.A. No. 2020-0880-JTL|CHTR=Charter Communications=nominal defendant=unknown=1091667;LBRDA=Liberty Broadband=defendant=bad=1611983|Liberty Broadband / John Malone|2020-10-13|||2023-07-19|350290|no|split||medium|Claims over Charter's 2020 share buyback deal with Liberty Broadband survive except against the independent committee directors. May 2 2022: summary judgment denied (op 332380).
walgreens-opioid-deriv|derivative (oversight) damages|Clem v. Skinner (Walgreens Boots Alliance)|Del. Ch.|C.A. No. 2021-0240-SG|WBA=Walgreens Boots Alliance=nominal defendant=unknown=1618921|Walgreens directors|2021-10-08|||2024-02-19|360250|no|dismissed||medium|Opioid-oversight claims (Walgreens agreed about $5.7B of opioid settlements) dismissed.
baker-ge-deriv|controlling-holder deal derivative|In re Baker Hughes, a GE Company, Derivative Litigation|Del. Ch.|C.A. No. 2019-0201-LWW|BKR=Baker Hughes=nominal defendant=unknown=1701605;GE=General Electric=defendant=good=40545|General Electric (former controller)|2019-03-11|||2023-04-17|346460|no|dismissed||medium|Special litigation committee's motion to end the derivative case over GE's 2018 sale of Baker Hughes stock was granted.
tesla-dircomp|director-pay derivative settlement|Police and Fire Retirement System of the City of Detroit v. Ellison (Tesla director pay)|Del. Ch.|C.A. No. 2020-0477-KSJM|TSLA=Tesla=nominal defendant=good=1318605|Tesla directors|2020-06-17|||2026-01-30|391030|no|settled|276616720|medium|Fee opinion on the settlement in which Tesla directors return about $277M of cash and stock (returned cash/stock figure from the opinion). Settlement was reached in 2023.
masimo-kiani|executive-pay / severance claim|Masimo Corporation v. Joe E. Kiani|Del. Ch.|C.A. No. 2024-1086|MASI=Masimo=plaintiff=bad=937556|Founder and former CEO Joe Kiani|2024-09-25|||2026-04-21|394720|no|dismissed||medium|Masimo's suit against its former CEO (seeking to void his roughly $450M change-of-control severance) dismissed. Saved 15:22 ET.
boeing-deriv-2026|derivative (oversight) damages|In re The Boeing Company Derivative Litigation (2024 complaints)|Del. Ch.|C.A. No. 2024-0450|BA=Boeing=nominal defendant=unknown=12927|Boeing directors and officers|2024-05-01|||2026-08-13|399780|no|dismissed||low|Oversight claims after the 2024 door-plug blowout dismissed for failure to show demand futility. Docket number and filing date estimated from the opinion list.
sirius-liberty|controlling-holder merger class action|Fishel v. Liberty Media Corporation (Sirius XM / Liberty Sirius XM merger)|Del. Ch.|C.A. No. 2024-0479|SIRI=Sirius XM Holdings=defendant=mixed=908937|Liberty Media / Sirius XM committee directors|2024-05-08|||2026-04-13|394310|no|split||low|Claims over the 2024 Sirius XM-Liberty Sirius XM combination: dismissed against the special committee (Count II), kept against other defendants (Count III). Docket number and filing date estimated.
endeavor-takeprivate|controlling-holder take-private class action|In re Endeavor Group Holdings, Inc. Stockholders' Litigation|Del. Ch.|C.A. No. 2025-0228|EDR=Endeavor Group Holdings=defendant=unknown=1766363|Silver Lake (controller)|2025-03-01|||||no|pending||low|Challenge to Silver Lake's $13B take-private of Endeavor; only lead-plaintiff rulings so far (Jul and Sep 2025). Filing date estimated.
skechers-takeprivate|controlling-holder take-private class action|In re Skechers Class Action Merger Litigation|Del. Ch.|C.A. No. 2025-1281-LWW|SKX=Skechers U.S.A.=defendant=unknown=1065837|3G Capital / Greenberg family|2025-11-01|||||no|pending||low|Challenge to 3G Capital's $9.4B take-private of Skechers; lead-plaintiff ruling Aug 14 2026. Filing date estimated from the docket number.
wwe-ufc-merger|controlling-holder merger class action|In re World Wrestling Entertainment, Inc. Merger Litigation|Del. Ch.|C.A. No. 2023-1166|TKO=TKO Group Holdings=defendant=unknown=1973266|Vince McMahon / Endeavor|2023-11-17|||||no|pending||low|Challenge to the 2023 WWE-UFC merger forming TKO; May 26 2026 sanctions ruling only. Filing date estimated.
williams-poison-pill|takeover-defense injunction|In re The Williams Companies Stockholder Litigation|Del. Ch.|C.A. No. 2020-0707-KSJM|WMB=The Williams Companies=defendant=bad=107263|Williams stockholders|2020-08-24|||2021-02-26|317240|no|loss||medium|Post-trial: Williams' 2020 poison pill (a plan that dilutes any holder crossing 5%) struck down and permanently enjoined. Affirmed by the Supreme Court Nov 2021.
srs-shire-appeal|merger-agreement damages (appeal)|Shire US Holdings, Inc. v. Shareholder Representative Services LLC|Del. Supr.|No. 170, 2021|TAK=Takeda (Shire)=appellant=bad=1395064|Former Lumena Pharmaceuticals holders|2021-05-15|||2021-11-17|326630|no|loss||low|Supreme Court affirmed the Oct 2020 judgment that Shire breached the Lumena merger agreement; damages amount not extracted. Saved 16:04 ET.
albertsons-kroger|merger-agreement damages|Albertsons Companies, Inc. v. The Kroger Co.|Del. Ch.|C.A. No. 2024-1276-LWW|ACI=Albertsons Companies=plaintiff=unknown=1646972;KR=The Kroger Co.=defendant=unknown=56873|Kroger / Albertsons|2024-12-11|||||no|pending||high|Albertsons seeks the $600M break fee plus billions in damages after the FTC blocked the $24.6B merger; Kroger countersued. Only discovery rulings so far (Sep 2025, Jun 2026).
ussteel-cfius|deal-blocking order challenge|United States Steel Corporation v. Committee on Foreign Investment in the United States|D.C. Cir.|No. 25-1004|X=United States Steel=petitioner=good=1163302|CFIUS / President Biden (Nippon Steel merger block)|2025-01-06|||2025-06-18||no|withdrawn||low|U.S. Steel and Nippon Steel sued to overturn the Jan 3 2025 order blocking their $14.9B merger; the case was held while the new administration reviewed the deal, which closed Jun 18 2025 and the suit was dropped. Dates from U.S. Steel 8-Ks; court docket not checked.
verisk-acculynx|merger-agreement enforcement|Verisk Analytics, Inc. v. ExactLogix, Inc. (AccuLynx)|Del. Ch.|C.A. No. 2026-0023-BWD|VRSK=Verisk Analytics=plaintiff=bad=1442145|ExactLogix / AccuLynx holders (private)|2026-01-09|||2026-08-07|399420|no|loss||medium|Post-trial: Verisk lost its bid to walk away from its $2.35B AccuLynx purchase; court granted the sellers' counterclaim for specific performance (order to close), costs and interest. Filing date estimated from the docket number.
"""

if __name__ == "__main__":
    main()
