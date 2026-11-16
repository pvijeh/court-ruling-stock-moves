"""Every PTAB inter partes review (IPR) and post-grant review (PGR) trial with a
US-listed party, decided or still open from 2021-01-01 on, with stock moves.

Sources (all public, no login):
- P-TACTS public search (https://ptacts.uspto.gov/ptacts/ui/public-search). The
  page's own back end answers a proceeding-number prefix ("IPR2021") with every
  trial filed that year, and lists each trial's documents with the minute each was
  entered. The USPTO Open Data Portal PTAB API needs an API key, which we lack.
- Final written decision PDFs from the same public page (outcome from page 1).
- SEC company_tickers_exchange.json (ticker map), XBRL companyfacts (shares,
  revenue), EDGAR full-text search (8-K times).
- Yahoo daily bars; Polygon 1-minute bars (last ~2 years, POLYGON_API_KEY).

Run stages in order: python3 scripts/universe_ptab.py all
Raw downloads are cached under data/universe/ptab/raw/ (git-ignored).
Output: data/universe/ptab/cases.csv
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "ptab"
RAW = OUT / "raw"
ET = ZoneInfo("America/New_York")
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
WEB_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
PTACTS = "https://ptacts.uspto.gov/ptacts/public-informations"
START = date(2021, 1, 1)
YEARS = range(2019, date.today().year + 1)
_last: dict[str, float] = {}
_GAP = {"ptacts": 2.5, "sec.gov": 0.15, "yahoo": 2.0, "polygon": 12.5, "google": 1.5}


def _throttle(host: str) -> None:
    for key, gap in _GAP.items():
        if key in host:
            wait = _last.get(key, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[key] = time.time()


def cache_path(kind: str, key: str, ext: str = "json.gz") -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key)[-100:]
    digest = hashlib.sha1(key.encode()).hexdigest()[:8]
    p = RAW / kind / f"{safe}_{digest}.{ext}"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch(
    url: str,
    kind: str,
    key: str | None = None,
    post: dict | None = None,
    binary: bool = False,
    tries: int = 4,
) -> bytes | None:
    """HTTP GET/POST with throttling and a gzip disk cache (None on failure)."""
    p = cache_path(kind, key or url, "bin.gz" if binary else "json.gz")
    miss = p.with_suffix(".miss")
    if p.exists():
        return gzip.decompress(p.read_bytes())
    if miss.exists():
        return None
    host = urllib.parse.urlparse(url).hostname or ""
    headers = {"User-Agent": SEC_UA if host.endswith("sec.gov") else WEB_UA}
    for i in range(tries):
        _throttle(host)
        try:
            if post is not None:
                r = requests.post(url, json=post, headers=headers, timeout=180)
            else:
                r = requests.get(url, headers=headers, timeout=120)
        except requests.RequestException:
            time.sleep(3 * (i + 1))
            continue
        if r.status_code == 200:
            p.write_bytes(gzip.compress(r.content))
            return r.content
        if r.status_code == 429 and "yahoo" in host:
            break
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(15 * (i + 1))
            continue
        if r.status_code == 403 and host.startswith("ptacts"):
            # P-TACTS answers bursts with a short 403 block: back off, then retry
            time.sleep(120 * (i + 1))
            continue
        break
    code = r.status_code if "r" in dir() else 0
    if code not in (0, 403, 429):
        # a real "not found"; throttling and network errors are retried next run
        miss.write_text(str(code))
    return None


def fetch_json(url: str, kind: str, **kw):
    b = fetch(url, kind, **kw)
    if not b:
        return None
    try:
        return json.loads(b)
    except ValueError:
        return None


def et(ts_seconds: float | None) -> datetime | None:
    if not ts_seconds:
        return None
    return datetime.fromtimestamp(ts_seconds, UTC).astimezone(ET)


# ---------------------------------------------------------------- 1. universe


def proceedings() -> list[dict]:
    """Every IPR/PGR filed 2019 on (earlier filings decide before 2021)."""
    rows = []
    for t in ("IPR", "PGR"):
        for y in YEARS:
            body = {
                "proceedingNumber": f"{t}{y}",
                "patentNumber": None,
                "applicationNumber": None,
                "trailTypes": [t],
                "isMnNotice": False,
            }
            d = fetch_json(
                f"{PTACTS}/case-search", "search", key=f"search_{t}{y}", post=body
            )
            rows += d or []
    for r in rows:
        try:
            r["parties"] = json.loads(r.get("allPartiesInfo") or "{}")
        except ValueError:
            r["parties"] = {}
    return rows


# ---------------------------------------------------------------- 2. tickers

SUFFIX = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|ltd|limited|llc|l l c|lp|"
    r"l p|plc|s a|sa|ag|nv|n v|se|bv|b v|gmbh|kk|k k|oy|oyj|ab|asa|a s|as|spa|"
    r"the|holdings?|group|international|intl|d b a.*|et al|formerly.*)\b"
)


def norm(name: str) -> str:
    s = re.sub(r"/[a-z]{2,3}/?$|/new/?$", "", name.strip().lower())
    s = s.replace("&", " and ").replace(".com", "com")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\bet al\b.*", " ", s)
    for _ in range(3):
        s = SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def sec_listed() -> dict[str, tuple[str, str, str]]:
    """normalized SEC name -> (ticker, cik, SEC name), exchange-listed only."""
    d = fetch_json(
        "https://www.sec.gov/files/company_tickers_exchange.json", "sec_tickers"
    )
    out: dict[str, tuple[str, str, str]] = {}
    for cik, name, tic, exch in d["data"]:
        if exch not in ("Nasdaq", "NYSE", "CBOE") or not tic:
            continue
        k = norm(name)
        # keep the first (main) class of shares per company
        if k and k not in out:
            out[k] = (tic.replace(".", "-"), str(cik), name)
    return out


# Hand-made map for subsidiaries and former names: regex on the normalized party
# name -> ticker of the listed parent. (ticker, first, last) limits the dates the
# parent was listed under that ticker; prices for delisted tickers may be missing.
ALIASES: list[tuple[str, str]] = [
    (r"^(google|youtube|waymo|fitbit|nest labs|verily)\b", "GOOGL"),
    (
        r"^(amazon|amazoncom|amzn mobile|aws|twitch|ring llc|whole foods|zoox|eero|audible)\b",
        "AMZN",
    ),
    (r"^(comcast|nbcuniversal|sky uk|xfinity)\b", "CMCSA"),
    (r"^(facebook|instagram|whatsapp|meta platforms|oculus)\b", "META"),
    (r"^(ericsson|telefonaktiebolaget lm ericsson|cradlepoint)\b", "ERIC"),
    (r"^(dell|emc\b|dell emc)", "DELL"),
    (r"^(cellco|verizon)\b", "VZ"),
    (r"^(nokia|alcatel lucent)\b", "NOK"),
    (r"^t mobile\b|^sprint\b", "TMUS"),
    (r"^(at and t|att|directv)\b", "T"),
    (r"^juniper networks", "JNPR"),
    (r"^(rovi|tivo|adeia|xperi)\b", "ADEA"),
    (r"^(dish|sling tv|echostar|hughes network)\b", "SATS"),
    (r"^(nxp|freescale)\b", "NXPI"),
    (r"^sharkninja\b", "SN"),
    (r"^(webroot|carbonite|open text|micro focus)\b", "OTEX"),
    (r"^micron\b", "MU"),
    (r"^(western digital|sandisk)\b", "WDC"),
    (r"^merck sharp|^msd\b", "MRK"),
    (r"^sony\b", "SONY"),
    (r"^qualcomm\b", "QCOM"),
    (r"^commscope\b", "COMM"),
    (r"^abbott\b", "ABT"),
    (r"^(charter communications|spectrum management|spectrum gulf coast)", "CHTR"),
    (r"^(r j reynolds|rai innovations|rai services|british american tobacco)", "BTI"),
    (r"^altria\b", "MO"),
    (r"^philip morris\b", "PM"),
    (r"^halliburton\b", "HAL"),
    (r"^(mylan|viatris)\b", "VTRS"),
    (r"^alcon\b", "ALC"),
    (r"^toyota\b", "TM"),
    (r"^(allergan|zeltiq|abbvie|pharmacyclics)\b", "ABBV"),
    (r"^(amo |amo$|johnson and johnson|janssen|ethicon|depuy|auris health)", "JNJ"),
    (r"^(hulu|disney|espn)\b", "DIS"),
    (r"^netflix\b", "NFLX"),
    (r"^(ati technologies|advanced micro devices|xilinx)\b", "AMD"),
    (r"^(medtronic|covidien)\b", "MDT"),
    (r"^gm global|^general motors", "GM"),
    (r"^halozyme\b", "HALO"),
    (r"^vivint\b", "VVNT"),
    (r"^american honda|^honda motor", "HMC"),
    (r"^(danaher|beckman coulter|cepheid|leica)\b", "DHR"),
    (r"^philips\b", "PHG"),
    (r"^sierra wireless\b", "SWIR"),
    (r"^draftkings\b", "DKNG"),
    (r"^intouch technologies", "TDOC"),
    (r"^ppc broadband\b", "BDC"),
    (r"^fedex\b", "FDX"),
    (r"^vmware\b", "VMW"),
    (r"^irobot\b", "IRBT"),
    (r"^home depot\b", "HD"),
    (r"^skechers\b", "SKX"),
    (r"^fubotv\b", "FUBO"),
    (r"^opiant\b", "OPNT"),
    (r"^(square|block|cash app)\b", "XYZ"),
    (r"^avago|^broadcom\b", "AVGO"),
    (r"^zimmer\b", "ZBH"),
    (r"^genzyme\b|^sanofi\b", "SNY"),
    (r"^bank of america\b", "BAC"),
    (r"^(pacificorp|midamerican energy|berkshire hathaway energy)", "BRK-B"),
    (r"^(interstate power and light|wisconsin power and light)", "LNT"),
    (r"^masimo\b", "MASI"),
    (r"^weber\b$", "WEBR"),
    (r"^intel\b", "INTC"),
    (r"^(apple)\b", "AAPL"),
    (r"^microsoft\b|^linkedin\b|^github\b|^activision", "MSFT"),
    (r"^(hewlett packard enterprise|aruba networks)", "HPE"),
    (r"^(hp\b|hp inc|hewlett packard\b(?! enterprise))", "HPQ"),
    (r"^cisco\b", "CSCO"),
    (r"^crown (\w+ )*gaming|^crown (dfs|pa dfs|dfs malta|europe malta|dk can)", "DKNG"),
    (r"^dk crown", "DKNG"),
    (r"^compass pathfinder", "CMPS"),
    (r"^frontier communications", "FYBR"),
    (r"^nevro\b", "NVRO"),
    (r"^(wells fargo|wfc holdings)\b", "WFC"),
    (r"^inari medical", "NARI"),
    (r"^vizio\b", "VZIO"),
    (r"^nabors\b", "NBR"),
    (r"^red hat\b", "IBM"),
    (r"^(hill rom|welch allyn)\b", "BAX"),
    (r"^twitter\b", "TWTR"),
    (r"^(nice systems|mattersight)\b", "NICE"),
    (r"^wright medical", "SYK"),
    (r"^midamerican funding", "BRK-B"),
    (r"^madison gas and electric", "MGEE"),
    (r"^wisconsin public service", "WEC"),
    (r"^hillman group", "HLMN"),
    (r"^sap labs", "SAP"),
    (r"^tsmc\b", "TSM"),
    (
        r"^(crown jade|polaris (powerled|innovations)|radian memory|southern visions|"
        r"sound (view|design|moderation)|intelligent (wellhead|clearing|automation)|"
        r"quantum (metric|imaging|design)|reliance (new energy|industries)|"
        r"noble (research|innovations)|meridian wildlife|national steel car|"
        r"decent espresso|viking (drill|arm)|sinclair pharma|freedom to operate|"
        r"titan implement|novo nordisk foundation|ensign us|blackstone strategic|gree$)",
        "-",
    ),
    (r"^lg\b", "-"),
    (r"^samsung\b", "-"),
    (r"^neonode smartphone\b", "-"),  # patent-assertion buyer, not Neonode Inc.
]

_ALIAS_RE = [(re.compile(p), t) for p, t in ALIASES]
GENERIC = {
    "american",
    "general",
    "national",
    "united",
    "first",
    "global",
    "advanced",
    "digital",
    "applied",
    "universal",
    "international",
    "new",
    "power",
    "data",
    "smart",
    "mobile",
    "net",
    "wireless",
    "health",
    "solutions",
    "systems",
}


# raw names unrelated to the listed company they normalise to (checked by hand)
_RAW_UNLISTED = re.compile(
    r"^(meridian international\b"
    r"|biofrontera ag\b)"  # former German parent of Biofrontera Inc., not US-listed
)


def match_party(name: str, sec: dict) -> tuple[str, str]:
    """(ticker, method) for a party name; ticker '' if none, '-' if known unlisted."""
    k = norm(name)
    if not k:
        return "", ""
    if _RAW_UNLISTED.search(name.lower()):
        return "-", "alias"
    for rx, tic in _ALIAS_RE:
        if rx.search(k):
            return tic, "alias"
    if k in sec:
        return sec[k][0], "exact"
    k2 = re.sub(r"\b(usa|u s a|us|america|north america|of america)\b", " ", k)
    k2 = re.sub(r"\s+", " ", k2).strip()
    if k2 in sec:
        return sec[k2][0], "exact_no_country"
    toks = k.split()
    for n in (3, 2, 1):
        if len(toks) > n:
            pre = " ".join(toks[:n])
            if pre in sec and (n > 1 or (len(pre) >= 5 and pre not in GENERIC)):
                return sec[pre][0], "prefix"
    return "", ""


def kept(r: dict) -> bool:
    td = r.get("terminationDate")
    return (not td) or et(int(td) / 1000).date() >= START


def listed_parties() -> list[dict]:
    """One record per proceeding per US-listed party (ticker)."""
    sec = sec_listed()
    out = []
    for r in proceedings():
        if not kept(r):
            continue
        sides = {}
        for side, role in (
            ("petitioner", "petitioner"),
            ("patentOwner", "patent_owner"),
        ):
            s = r["parties"].get(side) or {}
            names = [s.get("realParty")] + (s.get("additionalPartyList") or [])
            tics: dict[str, tuple[str, str]] = {}
            for n in names:
                if not n:
                    continue
                t, how = match_party(n, sec)
                if t and t != "-" and t not in tics:
                    tics[t] = (n.strip(), how)
            sides[role] = tics
        both = set(sides["petitioner"]) & set(sides["patent_owner"])
        for role, other in (
            ("petitioner", "patent_owner"),
            ("patent_owner", "petitioner"),
        ):
            for t, (n, how) in sides[role].items():
                if t in both:
                    continue
                out.append(
                    {
                        "proc": r,
                        "ticker": t,
                        "party_name": n,
                        "match": how,
                        "role": role,
                        "counter_tickers": " ".join(sorted(sides[other])),
                    }
                )
    return out


# ---------------------------------------------------------------- 3. documents


def artifacts(number: str) -> list[dict]:
    d = fetch_json(
        f"{PTACTS}/proceeding-artifacts?proceedingNumber={number}",
        "artifacts",
        key=number,
    )
    return d if isinstance(d, list) else []


def fetch_all_artifacts() -> None:
    def rank(r: dict) -> int:
        st = r.get("statusDisplay") or ""
        if st.startswith("Final Written") or "Director Review" in st:
            return 0
        if "Denied" in st or "Denial" in st or "Instituted" in st:
            return 1
        return 2

    procs = {x["proc"]["proceedingNumber"]: x["proc"] for x in listed_parties()}
    nums = sorted(procs, key=lambda n: (rank(procs[n]), n))
    print(len(nums), "proceedings with a listed party", file=sys.stderr)
    for i, n in enumerate(nums):
        artifacts(n)
        if i % 200 == 0:
            print(i, n, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 4. prices

BIO_BENCH = "XBI"
MKT_BENCH = "SPY"


def yahoo(
    sym: str, cached_only: bool = False
) -> dict[date, tuple[float, float, float]]:
    """Daily (adjusted close, close, volume) from the Yahoo chart API (empty if missing)."""
    if cached_only and not cache_path("yahoo", f"yahoo_{sym}").exists():
        return {}
    p1 = int(datetime(2018, 6, 1).timestamp())
    p2 = int(datetime.now().timestamp())
    ysym = sym.replace(".", "-")
    d = fetch_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}"
        f"?period1={p1}&period2={p2}&interval=1d&events=div,splits",
        "yahoo",
        key=f"yahoo_{sym}",
    )
    try:
        res = d["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    except (TypeError, KeyError, IndexError):
        return {}
    return {
        et(t).date(): (a, c, v or 0)
        for t, a, c, v in zip(ts, adj, q["close"], q["volume"])
        if a is not None and c is not None
    }


def polygon_daily(
    sym: str, cached_only: bool = False
) -> dict[date, tuple[float, float, float]]:
    """Daily (split-adjusted close twice, volume) from Polygon; the free plan covers about
    2 years. Used only where Yahoo has no data."""
    key = f"pd_{sym}"
    p = cache_path("polygon", key)
    api = os.environ.get("POLYGON_API_KEY")
    if (cached_only or not api) and not p.exists():
        return {}
    start = date.fromordinal(date.today().toordinal() - 730)
    d = fetch_json(
        f"https://api.polygon.io/v2/aggs/ticker/{sym.replace('-', '.')}/range/1/day/"
        f"{start}/{date.today()}?adjusted=true&sort=asc&limit=50000&apiKey={api}",
        "polygon",
        key=key,
    )
    return {
        et(b["t"] / 1000).date(): (b["c"], b["c"], b.get("v") or 0)
        for b in (d or {}).get("results") or []
    }


def daily(sym: str) -> tuple[dict[date, tuple[float, float, float]], str]:
    """Cached daily prices and their source: Yahoo first, else Polygon (last ~2 years)."""
    y = yahoo(sym, cached_only=True)
    if y:
        return y, "yahoo"
    p = polygon_daily(sym, cached_only=True)
    return p, ("polygon" if p else "")


def fetch_polygon_daily() -> None:
    tics = [MKT_BENCH, BIO_BENCH] + sorted({x["ticker"] for x in listed_parties()})
    for t in tics:
        if not yahoo(t, cached_only=True):
            polygon_daily(t)


def fetch_all_prices() -> None:
    tics = sorted({x["ticker"] for x in listed_parties()} | {MKT_BENCH, BIO_BENCH})
    miss, fails = [], 0
    for t in tics:
        if yahoo(t):
            fails = 0
            continue
        miss.append(t)
        fails += 1
        if fails >= 5:
            sys.exit("Yahoo is throttling (5 failures in a row); rerun later")
    print(len(tics), "tickers;", len(miss), "missing:", " ".join(miss), file=sys.stderr)


# ---------------------------------------------------------------- 4b. SEC XBRL

REV_TAGS = (
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "Revenues"),
    ("us-gaap", "SalesRevenueNet"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ("ifrs-full", "Revenue"),
)
# CIKs for tickers that left the SEC's current ticker file (acquired/delisted)
EXTRA_CIK = {
    "TWTR": "1418091",
    "NVRO": "1444380",
    "NARI": "1531048",
    "VZIO": "1835591",
    # looked up with EDGAR company search (efts.sec.gov search-index)
    "JNPR": "1043604",
    "FYBR": "20520",
    "IRBT": "1159167",
    "MASI": "937556",
    "OPNT": "1385508",
    "SATS": "1415404",
    "SKX": "1065837",
    "SWIR": "1111863",
    "VMW": "1124610",
    "WEBR": "1857951",
}


def ticker_cik() -> dict[str, str]:
    m = {t: c for t, c, _ in sec_listed().values()}
    d = fetch_json(
        "https://www.sec.gov/files/company_tickers_exchange.json", "sec_tickers"
    )
    for cik, _, tic, _ in d["data"]:
        if tic:
            m.setdefault(tic.replace(".", "-"), str(cik))
    return {**EXTRA_CIK, **m}


def companyfacts(cik: str) -> dict:
    """Compact facts: shares [(end, filed, val)], revenue [(start, end, filed, val, unit)]."""
    p = cache_path("xbrl_compact", cik)
    if p.exists():
        return json.loads(gzip.decompress(p.read_bytes()))
    raw = fetch(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
        "xbrl",
        key=f"cf_{cik}",
    )
    out: dict = {"shares": [], "revenue": []}
    if raw:
        f = json.loads(raw).get("facts", {})
        for u in (
            f.get("dei", {})
            .get("EntityCommonStockSharesOutstanding", {})
            .get("units", {})
            .values()
        ):
            out["shares"] += [(x["end"], x["filed"], x["val"]) for x in u]
        for ns, tag in REV_TAGS:
            for unit, xs in f.get(ns, {}).get(tag, {}).get("units", {}).items():
                out["revenue"] += [
                    (x.get("start"), x["end"], x["filed"], x["val"], unit)
                    for x in xs
                    if x.get("start")
                ]
        # the full file is large; keep only the compact form
        cache_path("xbrl", f"cf_{cik}").unlink(missing_ok=True)
    p.write_bytes(gzip.compress(json.dumps(out).encode()))
    return out


def facts_at(cik: str, day: date) -> tuple[float | None, float | None, str]:
    """(shares, TTM revenue, revenue unit) as filed on or before `day`."""
    cf = companyfacts(cik)
    ds = day.isoformat()
    sh = [s for s in cf["shares"] if s[1] <= ds]
    shares = max(sh, key=lambda s: (s[0], s[1]))[2] if sh else None
    best = None
    for start, end, filed, val, unit in cf["revenue"]:
        if filed > ds:
            continue
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days
        if 350 <= span <= 380 and (best is None or (end, filed) > (best[0], best[1])):
            best = (end, filed, val, unit)
    if not best:
        return shares, None, ""
    return shares, float(best[2]), best[3]


def fetch_all_facts() -> None:
    m = ticker_cik()
    tics = sorted({x["ticker"] for x in listed_parties()})
    miss = [t for t in tics if t not in m]
    print("no CIK:", " ".join(miss), file=sys.stderr)
    for t in tics:
        if t in m:
            companyfacts(m[t])
    print("facts done", file=sys.stderr)


def sic(cik: str) -> str:
    """SEC SIC industry code (used to pick the XBI benchmark for biotech/pharma)."""
    d = fetch_json(
        f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
        "sec_sub",
        key=f"sub_{cik}",
    )
    return str((d or {}).get("sic") or "")


def fetch_all_sic() -> None:
    m = ticker_cik()
    for t in sorted({x["ticker"] for x in listed_parties()}):
        if t in m:
            sic(m[t])
    print("sic done", file=sys.stderr)


# ---------------------------------------------------------------- 5. rows

COLUMNS = (
    "case_id case_type case_name court docket_number docket_url ticker company "
    "company_role counterparty counterparty_ticker filed_date trial_start_date "
    "trial_end_date decision_date decision_time_et decision_known_in_advance "
    "decision_source_url outcome outcome_for_company days_filed_to_decision "
    "market_cap_usd_at_filing revenue_ttm_usd_at_filing revenue_at_stake_usd "
    "revenue_at_stake_share ret_filing_day abn_ret_filing_day ret_decision_day "
    "abn_ret_decision_day ret_decision_plus5 adv_usd_20d_before_decision "
    "implied_move_before_decision settlement_amount_usd confidence sources notes "
    "first_public_source first_public_time_et time_precision during_market_hours "
    "company_release_time_et lead_minutes_vs_company_release minutes_to_half_move "
    "minute_data_available"
).split()
FWD_CODES = {"TDD", "FINAL DECN", "FINAL:RMD"}
INST_CODES = {"INSTITUTE DECN", "DGI", "DDI", "DM"}
FWD_RX = re.compile(r"final\s+written\s+decision", re.I)
# orders that only mention the final decision (deadline extensions, notices)
NOT_FWD_RX = re.compile(
    r"^\s*(order\b|authoriz|extend|notice|grant of good cause)|one-year", re.I
)
INST_RX = re.compile(
    r"(denying|granting|deny|grant)\w*\s+institution|institution\s+decision", re.I
)
TERM_RX = re.compile(r"terminat|settle|dismiss|adverse judgment|withdraw", re.I)
BIO_SIC = {"2833", "2834", "2835", "2836", "8731"}
OPEN, CLOSE = (9, 30), (16, 0)


def ms_date(v) -> date | None:
    return et(int(v) / 1000).date() if v else None


def artifacts_cached(number: str) -> list[dict] | None:
    p = cache_path("artifacts", number)
    if not p.exists():
        return None
    d = json.loads(gzip.decompress(p.read_bytes()))
    return [a for a in d if isinstance(a, dict)] if isinstance(d, list) else []


def doc_url(a: dict) -> str:
    if not a.get("artifactIdentifer") or not a.get("petitionIdentifier"):
        return ""
    return (
        f"{PTACTS}/petitions/{a['petitionIdentifier']}/download-documents"
        f"?artifactId={a['artifactIdentifer']}"
    )


def fwd_result(text: str) -> str:
    """'all' / 'some' / 'none' challenged claims held unpatentable, '' if unclear."""
    t = re.sub(r"\s+", " ", text or "").lower()
    if re.search(r"\bsome\b[^.;]{0,40}claims?", t):
        return "some"
    shown = re.search(
        r"\ball\b[^.;]{0,40}claims?[^.;]{0,40}\bunpatentable|"
        r"claims? [\d ,\-–and]+ (are|is|have been shown to be) unpatentable",
        t,
    )
    not_shown = re.search(
        r"\bno\b[^.;]{0,30}claims?[^.;]{0,30}unpatentable|"
        r"not (been )?(shown|proven|established|demonstrated)[^.;]{0,60}unpatentable|"
        r"not unpatentable",
        t,
    )
    if shown and not_shown:
        return "some"
    return "all" if shown else "none" if not_shown else ""


def kind_of(r: dict) -> str:
    st, tt = r.get("statusDisplay") or "", (r.get("terminationType") or "").lower()
    # the termination type is more specific than the status label
    if "adverse" in tt:
        return "adverse"
    if tt == "institution denied":
        return "denied"
    if st.startswith("Final Written") or (
        "Director Review" in st and "denied" not in tt
    ):
        return "fwd"
    if "Denied" in st or "Denial" in st or "Director Review" in st:
        return "denied"
    if st.startswith("Terminated-Settled"):
        return "settled"
    if st.startswith("Terminated-Adverse") or "adverse" in tt:
        return "adverse"
    if st.startswith("Terminated"):
        if "denied" in tt:
            return "denied"
        return "withdrawn" if "withdr" in tt else "dismissed"
    return "pending"


def final_docs(arts: list[dict] | None) -> list[dict]:
    """Board final written decisions (original, public versions and remands), oldest first."""
    board = sorted(
        (
            a
            for a in arts or []
            if a.get("filingParty") == "BOARD" and a.get("filingDate")
        ),
        key=lambda a: a["filingDate"],
    )
    out = [
        a
        for a in board
        if a.get("documentTypeCode") in FWD_CODES
        or (a.get("documentTypeCode") or "").startswith("FINAL")
        or (
            FWD_RX.search(a.get("name") or "")
            and not NOT_FWD_RX.search(a.get("name") or "")
        )
    ]
    return [a for a in out if "expunged" not in (a.get("name") or "").lower()]


def final_doc_near(docs: list[dict], day: date | None, days: int = 3) -> dict | None:
    """The final decision posted within a few days of the case's end date (public first)."""
    if not day:
        return None
    near = [a for a in docs if abs((et(a["filingDate"]).date() - day).days) <= days]
    near.sort(
        key=lambda a: (
            (a.get("availability") or "").strip() != "Public",
            a["filingDate"],
        )
    )
    return near[0] if near else None


def event(r: dict, arts: list[dict] | None) -> dict:
    """The event that ended the case, with its PTAB posting time when known."""
    kind = kind_of(r)
    inst = ms_date(r.get("institutionDecisionDate"))
    term = ms_date(r.get("terminationDate"))
    board = sorted(
        (
            a
            for a in arts or []
            if a.get("filingParty") == "BOARD" and a.get("filingDate")
        ),
        key=lambda a: a["filingDate"],
    )
    is_fwd = final_docs(arts)
    doc = None
    if (
        kind == "fwd"
        and arts
        and not is_fwd
        and "dismiss" in (r.get("terminationType") or "").lower()
    ):
        kind = "dismissed"  # the decision was expunged and the case dismissed
    if kind == "fwd":
        orig = [
            a
            for a in is_fwd
            if "remand" not in (a.get("name") or "").lower()
            and a.get("documentTypeCode") != "FINAL:RMD"
        ]
        coded = [
            a
            for a in orig
            if a.get("documentTypeCode") in FWD_CODES
            or (a.get("documentTypeCode") or "").startswith("FINAL")
        ]
        # a decision on remand that ends the case replaces the original decision
        doc = final_doc_near(is_fwd, term) or (coded or orig or is_fwd or [None])[0]
        day = term
    elif kind == "denied":
        c = [
            a
            for a in board
            if a.get("documentTypeCode") in INST_CODES
            or INST_RX.search(a.get("name") or "")
        ]
        ref = inst or term
        if c and ref:
            doc = min(c, key=lambda a: abs((et(a["filingDate"]).date() - ref).days))
        day = ref
    elif kind == "pending":
        day = None
    else:
        c = [
            a
            for a in board
            if (a.get("documentTypeCode") or "").startswith(("TERM", "ADVR"))
            or (a.get("documentTypeCode") == "TDD" and a not in is_fwd)
            or TERM_RX.search(a.get("name") or "")
        ]
        if c and term:
            doc = min(c, key=lambda a: abs((et(a["filingDate"]).date() - term).days))
        day = term
    ev = {
        "kind": kind,
        "inst": inst,
        "day": day,
        "dt": None,
        "doc": doc,
        "result": "",
        "public": True,
        "public_doc": None,
    }
    if doc:
        dt = et(doc["filingDate"])
        # some documents carry only a date (stamped 00:00 ET)
        if (dt.hour, dt.minute, dt.second) == (0, 0, 0):
            ev["date_only"] = True
        # trust the document time only if it is the same day the case record shows
        if day is None or abs((dt.date() - day).days) <= 3:
            ev["dt"], ev["day"] = (None if ev.get("date_only") else dt), dt.date()
        ev["public"] = (doc.get("availability") or "").strip() == "Public"
        if kind == "fwd":
            ev["result"] = fwd_result(doc.get("name") or "")
            if not ev["public"]:
                pub = [
                    a
                    for a in is_fwd
                    if "public" in (a.get("name") or "").lower()
                    and (a.get("availability") or "").strip() == "Public"
                ]
                ev["public_doc"] = pub[0] if pub else None
    return ev


def filed_at(r: dict, arts: list[dict] | None) -> tuple[date | None, datetime | None]:
    pet = sorted(
        (
            a
            for a in arts or []
            if a.get("filingParty") == "PETITIONER" and a.get("filingDate")
        ),
        key=lambda a: a["filingDate"],
    )
    if pet:
        dt = et(pet[0]["filingDate"])
        return dt.date(), dt
    ts = r.get("prcdCreatedTs") or ""
    return (date.fromisoformat(ts[:10]) if ts else None), None


class Prices:
    def __init__(self) -> None:
        self.cache: dict[str, dict] = {}
        self.days = sorted(daily(MKT_BENCH)[0])

    def px(self, sym: str) -> dict:
        if sym not in self.cache:
            self.cache[sym] = daily(sym)[0]
        return self.cache[sym]

    def event_index(self, day: date, dt: datetime | None) -> int | None:
        """Index into trading days of the first session that could react."""
        import bisect

        i = bisect.bisect_left(self.days, day)
        if i >= len(self.days):
            return None
        if dt and self.days[i] == day and (dt.hour, dt.minute) >= CLOSE:
            i += 1
        return i if i < len(self.days) else None

    def ret(self, sym: str, i0: int, i1: int) -> float | None:
        """Close of trading day i0-1 to close of day i1."""
        p = self.px(sym)
        if i0 < 1 or i1 >= len(self.days):
            return None
        a, b = p.get(self.days[i0 - 1]), p.get(self.days[i1])
        return b[0] / a[0] - 1 if a and b and a[0] else None

    def adv(self, sym: str, i: int) -> float | None:
        p = self.px(sym)
        v = [p[d][1] * p[d][2] for d in self.days[max(0, i - 20) : i] if d in p]
        return sum(v) / len(v) if len(v) >= 10 else None

    def close_on(self, sym: str, day: date) -> float | None:
        import bisect

        p = self.px(sym)
        i = bisect.bisect_right(self.days, day) - 1
        while i >= 0 and self.days[i] not in p:
            i -= 1
        return p[self.days[i]][1] if i >= 0 else None


def market_hours(dt: datetime | None, days: set) -> str:
    if dt is None:
        return "unknown"
    ok = dt.date() in days and OPEN <= (dt.hour, dt.minute) < CLOSE
    return "yes" if ok else "no"


def fmt(x: float | None, nd: int = 4) -> str:
    return "" if x is None else f"{x:.{nd}f}"


OUTCOME = {
    ("fwd", "all", "petitioner"): "win",
    ("fwd", "all", "patent_owner"): "loss",
    ("fwd", "none", "petitioner"): "loss",
    ("fwd", "none", "patent_owner"): "win",
    ("fwd", "amend_split", "petitioner"): "split",
    ("fwd", "amend_split", "patent_owner"): "split",
    ("fwd", "amend_denied", "petitioner"): "win",
    ("fwd", "amend_denied", "patent_owner"): "loss",
    ("fwd", "some", "petitioner"): "split",
    ("fwd", "some", "patent_owner"): "split",
}
FOR_CO = {"win": "good", "loss": "bad", "split": "mixed"}
KIND_LABEL = {
    "fwd": "final written decision",
    "denied": "institution denied (Board refused to hold a trial)",
    "settled": "terminated on settlement",
    "dismissed": "dismissed",
    "withdrawn": "withdrawn",
    "adverse": "adverse judgment (patent owner gave up the challenged claims)",
    "pending": "pending",
}


def fwd_text(doc: dict) -> str:
    """First and last pages of a final written decision PDF (text only is cached)."""
    key = str(doc["artifactIdentifer"])
    p = cache_path("fwd_text", key, "txt.gz")
    if p.exists():
        return gzip.decompress(p.read_bytes()).decode()
    raw = fetch(doc_url(doc), "pdf", key=key, binary=True)
    text = ""
    if raw:
        from pypdf import PdfReader

        try:
            pages = PdfReader(io.BytesIO(raw)).pages
            keep = list(range(min(2, len(pages)))) + list(
                range(max(2, len(pages) - 4), len(pages))
            )
            text = "\n".join(pages[i].extract_text() or "" for i in keep)
        except Exception as e:  # noqa: BLE001 - damaged PDFs are recorded as empty
            text = f"[pdf error {type(e).__name__}]"
        cache_path("pdf", key, "bin.gz").unlink(missing_ok=True)
        p.write_bytes(gzip.compress(text.encode()))
    return text


ORDER_SHOWN = re.compile(
    r"ordered[^.]{0,40}claims?[^.]{0,200}?(have|has) been (shown|proven|established)"
    r"[^.]{0,40}unpatentable",
    re.I,
)
ORDER_NOT = re.compile(
    r"claims?[^.]{0,200}?(have|has) not been (shown|proven|established)[^.]{0,40}unpatentable",
    re.I,
)


def fwd_result_pdf(text: str) -> str:
    t = re.sub(r"\s+", " ", text)
    cap = fwd_caption(t[:4000])
    if cap:
        return cap
    first = fwd_result(t[:3000])
    if first:
        return first
    shown, not_shown = ORDER_SHOWN.search(t), ORDER_NOT.search(t)
    if shown and not_shown:
        return "some"
    return "all" if shown else "none" if not_shown else ""


def fwd_caption(t: str) -> str:
    """Fallback on the caption under the title, e.g. 'Determining the Challenged Claim
    Unpatentable' or 'Granting-in-Part ... Motion to Amend'."""
    low = t.lower()
    m = re.search(
        r"determining (all |the |only |non-disclaimed |no |some |not all )*"
        r"(of the )?(challenged |original )?claims?( [\d,\-– and]+)? (not )?unpatentable",
        low,
    )
    if m:
        w = m.group(0)
        if re.search(r"\bsome\b|not all", w):
            return "some"
        if re.search(r"\bno\b|not unpatentable", w):
            return "none"
        return "all"
    if re.search(r"request to cancel all challenged claims", low):
        return "all"
    if re.search(
        r"granting[- ]in[- ]part[^.]{0,60}motion to amend|granting patent owner.s[^.]{0,30}motion to amend",
        low,
    ):
        return "amend_split"
    if re.search(r"denying patent owner.s[^.]{0,40}motion to amend", low):
        return "amend_denied"
    return ""


def fetch_fwd_pdfs() -> None:
    n = 0
    for x in listed_parties():
        r = x["proc"]
        ev = event(r, artifacts_cached(r["proceedingNumber"]))
        doc = ev["public_doc"] or ev["doc"]
        if ev["kind"] == "fwd" and not ev["result"] and doc and doc_url(doc):
            fwd_text(doc)
            n += 1
    print(n, "decision PDFs read", file=sys.stderr)


def first_hearing(arts: list[dict] | None) -> date | None:
    hs = [
        a["filingDate"]
        for a in arts or []
        if a.get("documentTypeCode") in ("HT", "OTH:HRTRANS") and a.get("filingDate")
    ]
    return et(min(hs)).date() if hs else None


def build() -> list[dict]:
    sec = sec_listed()
    sec_name = {}
    for t, _, n in sec.values():
        sec_name.setdefault(t, n)
    tcik = ticker_cik()
    P = Prices()
    days = set(P.days)
    rows = []
    for x in listed_parties():
        r, t, role = x["proc"], x["ticker"], x["role"]
        num = r["proceedingNumber"]
        arts = artifacts_cached(num)
        ev = event(r, arts)
        kind = ev["kind"]
        if ev["day"] and ev["day"] < START:
            continue  # decided before 2021 (later activity was a rehearing or appeal)
        notes: list[str] = [KIND_LABEL[kind]]
        conf = "low" if x["match"] == "prefix" else "medium"
        if arts is None:
            notes.append(
                "PTAB document list not downloaded; dates from the case record (day only)"
            )
        res = ev["result"]
        doc = ev["public_doc"] or ev["doc"]
        if kind == "fwd" and not res and doc and doc.get("artifactIdentifer"):
            p = cache_path("fwd_text", str(doc["artifactIdentifer"]), "txt.gz")
            if p.exists():
                res = fwd_result_pdf(gzip.decompress(p.read_bytes()).decode())
                if res:
                    notes.append("outcome read from the decision PDF")
        if kind == "fwd":
            outcome = OUTCOME.get(("fwd", res, role), "")
            if not outcome:
                notes.append("decision outcome not parsed; check the decision")
                conf = "low"
        elif kind == "denied":
            outcome = "loss" if role == "petitioner" else "win"
        elif kind == "adverse":
            outcome = "win" if role == "petitioner" else "loss"
        else:
            outcome = kind
        pet = (
            (r["parties"].get("petitioner") or {}).get("realParty")
            or r.get("petiRealParty")
            or ""
        )
        po = (
            (r["parties"].get("patentOwner") or {}).get("realParty")
            or r.get("poRealParty")
            or ""
        )
        fd, fdt = filed_at(r, arts)
        if x["match"] == "alias" or norm(x["party_name"]) != norm(sec_name.get(t, "")):
            notes.append(f"party in case: {x['party_name']} (listed as/under {t})")
        inst = ev["inst"]
        instituted = kind in ("fwd", "adverse") or (
            inst
            and kind in ("settled", "dismissed", "withdrawn", "pending")
            and "Before Institution" not in (r.get("terminationType") or "")
        )
        if kind == "fwd" and inst:
            dl = (
                inst.replace(year=inst.year + 1)
                if not (inst.month == 2 and inst.day == 29)
                else inst + (date(inst.year + 1, 3, 1) - inst)
            )
            notes.append(
                f"statutory deadline for the final decision {dl} (35 U.S.C. 316(a)(11): one year "
                f"after institution on {inst}, extendable by six months); exact day not announced"
            )
        if kind == "denied":
            notes.append(
                "institution decisions are due about three months after the patent owner's "
                "preliminary response (35 U.S.C. 314(b)); exact day not announced"
            )
        if kind == "fwd" and ev["doc"] and not ev["public"]:
            notes.append(
                "decision first posted to the parties only (sealed); public version "
                + (
                    f"posted {et(ev['public_doc']['filingDate']):%Y-%m-%d %H:%M}"
                    if ev["public_doc"]
                    else "not found"
                )
            )
        # first public appearance: the public decision document (sealed ones: the public version)
        pub_doc = ev["doc"] if ev["public"] else ev["public_doc"]
        pub_dt = et(pub_doc["filingDate"]) if pub_doc else None
        if pub_dt and (pub_dt.hour, pub_dt.minute, pub_dt.second) == (0, 0, 0):
            pub_dt = None
        day = ev["day"]
        if pub_dt and day and pub_dt.date() != day:
            # the chosen document is from another day (e.g. the original denial before a
            # rehearing); use the first Board document posted on the event day instead
            same = sorted(
                et(a["filingDate"])
                for a in arts or []
                if a.get("filingParty") == "BOARD"
                and a.get("filingDate")
                and et(a["filingDate"]).date() == day
            )
            same = [d for d in same if (d.hour, d.minute, d.second) != (0, 0, 0)]
            pub_dt = same[0] if same else None
        cik = tcik.get(t, "")
        bench = BIO_BENCH if cik and sic(cik) in BIO_SIC else MKT_BENCH
        ret_d = abn_d = ret5 = adv = None
        if day and P.px(t):
            i = P.event_index(day, pub_dt)
            if i is not None:
                two = pub_dt is None
                i1 = i + 1 if two else i
                ret_d, b = P.ret(t, i, i1), P.ret(bench, i, i1)
                abn_d = ret_d - b if ret_d is not None and b is not None else None
                ret5 = (
                    P.ret(t, i, min(i + 5, len(P.days) - 1))
                    if i + 5 < len(P.days)
                    else None
                )
                adv = P.adv(t, i)
                if two:
                    notes.append(
                        "decision time unknown: decision-day return is the 2-day return (day of + next)"
                    )
        ret_f = abn_f = None
        if fd and P.px(t):
            i = P.event_index(fd, fdt)
            if i is not None:
                ret_f, b = P.ret(t, i, i), P.ret(bench, i, i)
                abn_f = ret_f - b if ret_f is not None and b is not None else None
        if not P.px(t):
            notes.append(f"no Yahoo daily prices for {t} (delisted or renamed)")
        mcap = rev = None
        if cik and fd:
            shares, rv, unit = facts_at(cik, fd)
            px = P.close_on(t, fd)
            if rv is not None and unit != "USD":
                notes.append(
                    f"foreign filer reporting in {unit}: market cap and revenue left blank"
                )
            else:
                rev = rv
                mcap = shares * px if shares and px else None
        elif not cik:
            notes.append(f"no SEC CIK found for {t}")
        notes.append(f"benchmark {bench}")
        notes.append(
            "revenue at stake: not disclosed per patent; PTAB settlements are filed confidentially (35 U.S.C. 317(b))"
        )
        dts = ev["dt"]
        rows.append(
            {
                "case_id": num,
                "case_type": f"PTAB {r.get('trialType') or num[:3]}",
                "case_name": f"{pet} v. {po} (US patent {r.get('poPatentNumber') or '?'})",
                "court": "USPTO Patent Trial and Appeal Board",
                "docket_number": num,
                "docket_url": f"{PTACTS}/proceeding-artifacts?proceedingNumber={num}",
                "ticker": t,
                "company": sec_name.get(t, x["party_name"]),
                "company_role": role,
                "counterparty": po if role == "petitioner" else pet,
                "counterparty_ticker": x["counter_tickers"],
                "filed_date": fd or "",
                "trial_start_date": inst if instituted and inst else "",
                "trial_end_date": first_hearing(arts) or "",
                "decision_date": day or "",
                "decision_time_et": f"{dts:%H:%M}" if dts else "",
                "decision_known_in_advance": "no" if kind != "pending" else "",
                "decision_source_url": doc_url(doc) if doc else "",
                "outcome": outcome,
                "outcome_for_company": FOR_CO.get(outcome, "unknown"),
                "days_filed_to_decision": (day - fd).days if day and fd else "",
                "market_cap_usd_at_filing": fmt(mcap, 0),
                "revenue_ttm_usd_at_filing": fmt(rev, 0),
                "revenue_at_stake_usd": "",
                "revenue_at_stake_share": "",
                "ret_filing_day": fmt(ret_f),
                "abn_ret_filing_day": fmt(abn_f),
                "ret_decision_day": fmt(ret_d),
                "abn_ret_decision_day": fmt(abn_d),
                "ret_decision_plus5": fmt(ret5),
                "adv_usd_20d_before_decision": fmt(adv, 0),
                "implied_move_before_decision": "",
                "settlement_amount_usd": "",
                "confidence": conf,
                "sources": "P-TACTS public case search and document list; Yahoo daily prices; SEC XBRL companyfacts",
                "notes": "; ".join(notes),
                "first_public_source": (
                    "PTAB system (P-TACTS public document)"
                    if pub_doc
                    else "PTAB system (P-TACTS case status, date only)"
                    if day
                    else ""
                ),
                "first_public_time_et": f"{pub_dt:%Y-%m-%d %H:%M}"
                if pub_dt
                else (str(day) if day else ""),
                "time_precision": "minute" if pub_dt else ("day" if day else ""),
                "during_market_hours": market_hours(pub_dt, days) if day else "",
                "company_release_time_et": "",
                "lead_minutes_vs_company_release": "",
                "minutes_to_half_move": "",
                "minute_data_available": "",
            }
        )
        row = rows[-1]
        if material(row, sic(cik) if cik else "", r.get("poTechCenterId") or ""):
            row["notes"] += "; MATERIAL (rule-based flag, see docs)"
        src = daily(t)[1]
        row["sources"] = row["sources"].replace(
            "Yahoo daily prices",
            {
                "yahoo": "Yahoo daily prices",
                "polygon": "Polygon daily prices (Yahoo unavailable)",
            }.get(src, "no daily prices found"),
        )
    rows.sort(key=lambda d: (d["case_id"], d["ticker"]))
    return rows


def write(rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    print(len(rows), "rows ->", OUT / "cases.csv", file=sys.stderr)


# ---------------------------------------------------------------- 6. minute bars

MINUTE_DAYS = 730  # Polygon's free plan reaches back about two years


def polygon_minutes(
    sym: str, day: str, cached_only: bool
) -> list[tuple[datetime, float]]:
    key = f"pm_{sym}_{day}"
    p = cache_path("polygon", key)
    if cached_only and not p.exists():
        return []
    api = os.environ.get("POLYGON_API_KEY")
    if not api and not p.exists():
        return []
    d = fetch_json(
        f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/{day}/{day}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={api}",
        "polygon",
        key=key,
    )
    return [(et(b["t"] / 1000), b["c"]) for b in (d or {}).get("results") or []]


def half_move(bars: list[tuple[datetime, float]], t0: datetime) -> int | None:
    """Minutes from t0 until the price had made half its move from t0 to the close."""
    sess = [(t, c) for t, c in bars if OPEN <= (t.hour, t.minute) < CLOSE]
    before = [c for t, c in sess if t < t0]
    after = [(t, c) for t, c in sess if t >= t0]
    if not before or not after:
        return None
    p0, close = before[-1], after[-1][1]
    move = close - p0
    if abs(move) < 0.005 * p0:  # under half a percent: no move to time
        return None
    for t, c in after:
        if (c - p0) / move >= 0.5:
            return int((t - t0).total_seconds() // 60)
    return None


def add_minutes(rows: list[dict], cached_only: bool = True) -> None:
    cutoff = date.today().toordinal() - MINUTE_DAYS
    for r in rows:
        if r["time_precision"] != "minute" or not r["first_public_time_et"]:
            continue
        t0 = datetime.strptime(r["first_public_time_et"], "%Y-%m-%d %H:%M").replace(
            tzinfo=ET
        )
        if t0.date().toordinal() < cutoff:
            r["minute_data_available"] = "no"
            continue
        if r["during_market_hours"] != "yes":
            continue
        bars = polygon_minutes(r["ticker"], t0.date().isoformat(), cached_only)
        r["minute_data_available"] = "yes" if bars else ("" if cached_only else "no")
        if bars:
            m = half_move(bars, t0)
            r["minutes_to_half_move"] = "" if m is None else str(m)


# ---------------------------------------------------------------- 7. materiality, 8-Ks

HEALTH_SIC = BIO_SIC | {"3841", "3842", "3845", "3851", "2833"}


def material(r: dict, sic_code: str, tech_center: str) -> bool:
    """Patent likely covers a product that is a large share of the company's revenue."""
    rev = float(r["revenue_ttm_usd_at_filing"] or 0) or None
    health = sic_code in HEALTH_SIC or tech_center == "1600"
    if r["company_role"] == "patent_owner":
        if rev is not None and rev < 5e8:
            return True
        return health and rev is not None and rev < 2e9
    # a small drug or device maker challenging a patent that blocks its own product
    return health and rev is not None and rev < 1e9


def release_8k(cik: str, day: str) -> tuple[str, str]:
    """(acceptance time ET, URL) of the company's first 8-K/6-K mentioning the PTAB
    within three days of the decision, from EDGAR full-text search."""
    d0 = date.fromisoformat(day)
    end = date.fromordinal(d0.toordinal() + 3)
    q = urllib.parse.quote(
        '"Patent Trial and Appeal Board" OR "inter partes review" OR PTAB'
    )
    hits = fetch_json(
        f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=8-K,6-K"
        f"&dateRange=custom&startdt={d0}&enddt={end}&ciks={int(cik):010d}",
        "efts",
        key=f"efts2_{cik}_{day}",
    )
    best = ("", "")
    for h in sorted(
        (hits or {}).get("hits", {}).get("hits", []), key=lambda h: h["_id"]
    ):
        acc = h["_id"].split(":")[0]
        idx = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{acc.replace('-', '')}/{acc}-index.htm"
        )
        page = fetch(idx, "edgar_index", key=f"idx_{acc}")
        m = re.search(
            rb"Accepted</div>\s*<div class=\"info\">([\d-]+ [\d:]+)", page or b""
        )
        if m:
            t = m.group(1).decode()[:16]
            if not best[0] or t < best[0]:
                best = (t, idx)
    return best


def add_releases(rows: list[dict], cached_only: bool = True) -> None:
    """Company 8-K/6-K acceptance time for material rows with a decision (EDGAR full-text search)."""
    tcik = ticker_cik()
    for r in rows:
        cik = tcik.get(r["ticker"], "")
        if "MATERIAL" not in r["notes"] or not r["decision_date"] or not cik:
            continue
        day = str(r["decision_date"])
        if cached_only and not cache_path("efts", f"efts2_{cik}_{day}").exists():
            continue
        t, url = release_8k(cik, day)
        if not t:
            continue
        r["company_release_time_et"] = t
        r["sources"] += f"; company 8-K {url}"
        if r["time_precision"] == "minute":
            a = datetime.strptime(r["first_public_time_et"], "%Y-%m-%d %H:%M")
            b = datetime.strptime(t, "%Y-%m-%d %H:%M")
            r["lead_minutes_vs_company_release"] = str(
                int((b - a).total_seconds() // 60)
            )


def review(rows: list[dict]) -> None:
    """Check every material row and a fixed random 50 of the rest: the PTAB party name must
    be the listed company (pairs read by hand; wrong ones are in _RAW_UNLISTED) and the
    outcome must agree with a second reading of the decision (document title or caption
    for final decisions, the case record for denials and settlements). Agreeing rows
    become high confidence; the evidence goes to raw/review.csv."""
    import random

    lp = {(x["proc"]["proceedingNumber"], x["ticker"]): x for x in listed_parties()}
    mat = [r for r in rows if "MATERIAL" in r["notes"]]
    rest = [r for r in rows if "MATERIAL" not in r["notes"]]
    sample = random.Random(50).sample(rest, min(50, len(rest)))
    out = []
    for grp, part in (("material", mat), ("random50", sample)):
        for r in part:
            x = lp[(r["case_id"], r["ticker"])]
            pr = x["proc"]
            ev = event(pr, artifacts_cached(r["case_id"]))
            d = ev["public_doc"] or ev["doc"] or {}
            name = re.sub(r"\s+", " ", d.get("name") or "")
            txt = ""
            if d.get("artifactIdentifer"):
                p = cache_path("fwd_text", str(d["artifactIdentifer"]), "txt.gz")
                if p.exists():
                    txt = re.sub(r"\s+", " ", gzip.decompress(p.read_bytes()).decode())
            m = re.search(r"(Determining|Granting|Denying)[^.]{0,70}", txt[:4000])
            cap = m.group(0) if m else ""
            kind, o, role = ev["kind"], r["outcome"], r["company_role"]
            status = f"{pr.get('statusDisplay') or ''} {pr.get('terminationType') or ''}".lower()
            if kind == "fwd":
                want = {
                    "win": "all" if role == "petitioner" else "none",
                    "loss": "none" if role == "petitioner" else "all",
                    "split": "some",
                }.get(o)
                got = fwd_caption(cap) or fwd_caption(name) or fwd_result(cap)
                got = {"amend_split": "some", "amend_denied": "all"}.get(got, got)
                ok = bool(want) and got == want
            elif kind == "denied":
                ok = bool(
                    re.search(
                        r"den(y|ied|ying)|discretionary",
                        f"{name} {cap} {status}".lower(),
                    )
                )
            elif kind == "settled":
                ok = "settle" in status
            else:
                ok = o in ("pending", "dismissed") or kind == "adverse"
            if ok:
                r["confidence"] = "high"
                r["notes"] += (
                    f"; hand-check ({grp}): party and outcome agree with the PTAB record"
                )
            else:
                r["notes"] += (
                    f"; hand-check ({grp}): could not confirm the outcome, see the decision"
                )
            out.append(
                {
                    "group": grp,
                    "case_id": r["case_id"],
                    "ticker": r["ticker"],
                    "role": role,
                    "outcome": o,
                    "kind": kind,
                    "party": x["party_name"],
                    "company": r["company"],
                    "doc": name[:120],
                    "caption": cap[:100],
                    "status": status,
                    "agree": ok,
                }
            )
    with open(RAW / "review.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)


def summary(rows: list[dict]) -> None:
    """Headline numbers for docs/universe_ptab.md."""
    import statistics as stx
    from collections import Counter

    rows = [{k: "" if v is None else str(v) for k, v in r.items()} for r in rows]
    cases = {r["case_id"] for r in rows}
    print(
        "rows",
        len(rows),
        "cases",
        len(cases),
        "tickers",
        len({r["ticker"] for r in rows}),
    )
    yr = Counter((r["decision_date"] or "pending")[:4] for r in rows)
    print("rows by decision year", sorted(yr.items()))
    print(
        "cases by type",
        Counter(r["case_type"] for r in {r["case_id"]: r for r in rows}.values()),
    )
    print("outcome", Counter(r["outcome"] for r in rows).most_common())
    print("event kind", Counter(r["notes"].split(";")[0] for r in rows).most_common())
    print("role", Counter(r["company_role"] for r in rows))
    ab = [
        (abs(float(r["abn_ret_decision_day"])), r)
        for r in rows
        if r["abn_ret_decision_day"]
    ]
    print("with abnormal decision-day return", len(ab))
    for k in (0.05, 0.10, 0.25):
        print(f"  |abn| > {k:.0%}:", sum(a > k for a, _ in ab))
    if ab:
        print("  median |abn|", round(stx.median(a for a, _ in ab), 4))
    for a, r in sorted(ab, key=lambda x: -x[0])[:15]:
        print(
            "  ",
            r["abn_ret_decision_day"],
            r["ticker"],
            r["case_id"],
            r["company_role"],
            r["outcome"],
            r["decision_date"],
            r["decision_time_et"],
            r["confidence"],
        )
    fast = [
        r
        for r in rows
        if r["during_market_hours"] == "yes" and r["decision_known_in_advance"] == "no"
    ]
    print(
        "public during market hours, no preset date",
        len(fast),
        "of minute-timed",
        sum(r["time_precision"] == "minute" for r in rows),
    )
    lead = [
        float(r["lead_minutes_vs_company_release"])
        for r in fast
        if r["lead_minutes_vs_company_release"]
    ]
    half = [float(r["minutes_to_half_move"]) for r in fast if r["minutes_to_half_move"]]
    print("lead n", len(lead), "median", stx.median(lead) if lead else None)
    print("half-move n", len(half), "median", stx.median(half) if half else None)


BOARD_KINDS = ("final written decision", "institution denied", "adverse judgment")


def _pct(x: str) -> str:
    return f"{float(x):+.1%}"


def write_doc(rows: list[dict]) -> None:
    """Render docs/universe_ptab.md from the finished rows."""
    import statistics as stx
    from collections import Counter

    rows = [{k: "" if v is None else str(v) for k, v in r.items()} for r in rows]
    cases = {r["case_id"]: r for r in rows}
    n_t = len({r["ticker"] for r in rows})
    both = sum(n == 2 for n in Counter(r["case_id"] for r in rows).values())
    yr = Counter((r["decision_date"] or "")[:4] for r in cases.values())
    kinds = Counter(r["notes"].split(";")[0] for r in cases.values())
    out = Counter(r["outcome"] for r in rows)
    ofc = Counter(r["outcome_for_company"] for r in rows)
    ab = [r for r in rows if r["abn_ret_decision_day"]]
    a = [abs(float(r["abn_ret_decision_day"])) for r in ab]
    med = stx.median(a) if a else 0
    dec = [r for r in rows if r["decision_date"]]
    first_px = min((r["decision_date"] for r in ab), default="")

    def dedupe(rs: list[dict], n: int) -> list[dict]:
        seen, res = set(), []
        for r in sorted(rs, key=lambda r: -abs(float(r["abn_ret_decision_day"]))):
            k = (r["ticker"], r["decision_date"])
            if k not in seen:
                seen.add(k)
                res.append(r)
            if len(res) == n:
                break
        return res

    def line(r: dict, fast: bool = False) -> str:
        n_same = sum(
            1
            for x in rows
            if x["ticker"] == r["ticker"] and x["decision_date"] == r["decision_date"]
        )
        extra = f" ({n_same} trials decided that day)" if n_same > 1 else ""
        when = r["first_public_time_et"] if fast else r["decision_date"]
        half = (
            f", half the day's move within {r['minutes_to_half_move']} minutes"
            if fast and r["minutes_to_half_move"]
            else ""
        )
        return (
            f"- **{r['company']} ({r['ticker']})**, {r['company_role'].replace('_', ' ')} vs "
            f"{r['counterparty'][:40].strip()}: {r['case_id']}{extra}, {r['notes'].split(';')[0]}, "
            f"outcome for the company {r['outcome_for_company']}. Posted {when}; "
            f"abnormal move {_pct(r['abn_ret_decision_day'])}{half}."
        )

    mat = [r for r in rows if "MATERIAL" in r["notes"]]
    chk = [r for r in rows if "hand-check" in r["notes"]]
    hi = sum("party and outcome agree" in r["notes"] for r in chk)

    fast = [
        r
        for r in rows
        if r["during_market_hours"] == "yes"
        and r["decision_known_in_advance"] == "no"
        and r["notes"].startswith(BOARD_KINDS)
    ]
    fast_ab = [r for r in fast if r["abn_ret_decision_day"]]
    fast_min = [r for r in fast if r["minute_data_available"] == "yes"]
    half = [int(r["minutes_to_half_move"]) for r in fast if r["minutes_to_half_move"]]
    lead = [
        float(r["lead_minutes_vs_company_release"])
        for r in fast
        if r["lead_minutes_vs_company_release"]
    ]
    timed = sum(
        r["time_precision"] == "minute"
        for r in rows
        if r["notes"].startswith(BOARD_KINDS)
    )
    board = sum(r["notes"].startswith(BOARD_KINDS) for r in rows)
    L = [
        "# Patent office trials (PTAB) since 2021: the complete list and the stock moves",
        "",
        "**Summary**",
        f"- **What this is:** every patent office trial with a US-listed company on either side that was decided, "
        f"settled or still open from 2021-01-01 to {date.today()}. That is {len(cases):,} trials, "
        f"{len(rows):,} company rows and {n_t} tickers, in `data/universe/ptab/cases.csv`.",
        "- **Why it matters:** to estimate how much a stock moves when a patent trial ends, you need every trial, "
        "including the ones where nothing happened, not a list of famous ones.",
        "- **Where we looked:** the US Patent and Trademark Office's public trial system (P-TACTS), the decision "
        "documents themselves, SEC filings for company size and revenue, and Polygon for prices.",
        f"- **What we found:** the median decision-day move, after taking out the market's move, is "
        f"{med:.1%}. Only {sum(x > 0.10 for x in a)} of {len(a):,} measured rows moved more than 10%.",
        f"- **Speed:** {len(fast):,} Board decisions were posted while the market was open, on a day nobody "
        f"announced. Where 1-minute prices exist, the stock made half its move in a median "
        f"{stx.median(half) if half else 0:.0f} minutes.",
        f"- **Still open:** prices only go back to {first_px[:7]} (see below), so older decisions have no move.",
        "",
        "**Terms used here**",
        "- **PTAB** (Patent Trial and Appeal Board): the patent office's court. Anyone can ask it to cancel a patent.",
        "- **IPR** (inter partes review) and **PGR** (post-grant review): the two kinds of PTAB trial. A PGR must "
        "be filed within 9 months of the patent being granted and can use more grounds.",
        "- **Petitioner:** the side asking to cancel the patent, usually a company that has been sued over it. "
        "**Patent owner:** the side defending it.",
        "- **Institution:** the Board's decision, about 6 months after filing, on whether to hold a trial at all. "
        "**Institution denied** means no trial and the patent survives.",
        "- **Final written decision:** the ruling at the end of a trial, due by law about 12 months after "
        "institution. The Board does not announce the day or the time.",
        "- **Adverse judgment:** the patent owner gives up the challenged claims, which counts as a petitioner win.",
        "- **Abnormal return:** the stock's close-to-close return minus the benchmark's (the S&P 500 fund SPY, or "
        "the biotech fund XBI for drug and biotech companies). It strips out the market's move that day.",
        "",
        "**What was counted and how**",
        "- Every IPR and PGR filed from 2019 on was pulled from the public P-TACTS search; trials that ended "
        "before 2021 were dropped. The USPTO's official data API needs a key we don't have (it returns 401).",
        "- Party names were matched to SEC lists of exchange-listed companies, plus subsidiaries and former names "
        '("Google LLC" counts as Alphabet). Matches that looked wrong on reading were removed, for example '
        "Biofrontera AG (the German former parent) is not Biofrontera Inc.",
        f"- One row per trial per listed company. Both sides are listed in {both} trials, so they have two rows.",
        "- Final written decisions were read from the decision PDF: the line under the title says whether all, "
        "some or none of the challenged claims were cancelled.",
        "- The posting time is the minute the Board's document appeared in P-TACTS. A document posted after 4pm or "
        "on a weekend counts against the next trading day. Where only the date is known, the move is the 2-day "
        "return, and the notes say so.",
        "",
        "**How complete the list is**",
        "- The trial list itself should be complete for IPR and PGR: the search returns every trial number by year.",
        f"- The company matching is not complete. Private companies and patent-holding firms are correctly left out, "
        f"but a listed company filing under an unusual subsidiary name can be missed. {sum(r['confidence'] == 'low' for r in rows)} "
        "rows are marked low confidence; the notes say why.",
        f"- Outcomes are blank for {out['']} rows: the code could not read a result from the decision document "
        "or the trial status.",
        f"- Prices: Yahoo, the planned source, refused every request for the whole run (HTTP 429), so prices come "
        f"from Polygon's free tier, which goes back about 2 years. {len(ab):,} of {len(dec):,} decided rows have a "
        "decision-day move. Market value at filing is filled only where the filing date is inside that window.",
        "- Company press releases: listed companies almost never file an 8-K (the SEC form for material news) "
        "about a PTAB decision, so the company release time is nearly always blank.",
        "",
        "**Counts per year (trials, by the year the trial ended)**",
    ]
    L += [f"- {y}: {yr[y]:,}" for y in sorted(k for k in yr if k)]
    L += [f"- Still pending: {yr['']:,}", "", "**How the trials ended**"]
    L += [f"- {k}: {v:,} trials" for k, v in kinds.most_common()]
    L += [
        "",
        "**Outcome split (company rows)**",
        "- Petitioner rows: win means the patent's claims were cancelled; patent owner rows: win means the patent survived.",
    ]
    L += [f"- {k or 'blank'}: {v:,}" for k, v in out.most_common()]
    L += [
        f"- For the listed company: good {ofc['good']:,}, bad {ofc['bad']:,}, mixed {ofc['mixed']:,}, "
        f"unknown {ofc['unknown']:,} (settlements and dismissals are unknown)."
    ]
    L += [
        "",
        "**Stock moves on the decision day (abnormal, close to close)**",
        f"- Measured rows: {len(a):,}. Median absolute move: {med:.1%}.",
        f"- More than 5%: {sum(x > 0.05 for x in a)}. More than 10%: {sum(x > 0.10 for x in a)}. "
        f"More than 25%: {sum(x > 0.25 for x in a)}.",
        "- A move on the decision day does not prove the decision caused it. For large companies (Ford, Micron, "
        "Ericsson) a big move that day is almost certainly other news, such as earnings.",
        "",
        "**The 10 biggest moves**",
    ]
    L += [line(r) for r in dedupe(ab, 10)]
    L += [
        "",
        "**Which outcomes can be traded on fast**",
        "- Only the Board's own decisions count here (final written decisions, institution denials, adverse "
        "judgments). Settlements and dismissals are filed by the parties, who know the outcome first.",
        f"- {len(fast):,} of {board:,} Board-decision rows were posted while the market was open (9:30 to 16:00 ET) "
        f"on a day nobody announced in advance. {timed:,} of those {board:,} have a posting minute.",
        "- Median lead over the company's own release: "
        + (
            f"{stx.median(lead):.0f} minutes ({len(lead)} rows)."
            if lead
            else "not measurable; no company in these rows filed an 8-K with a time on the decision day."
        ),
        "- Median minutes to half the day's move: "
        + (
            f"{stx.median(half):.0f} minutes, over {len(half)} rows with 1-minute prices "
            f"({len(fast_min)} rows had minute data; a move too small to time leaves it blank)."
            if half
            else "not measured."
        ),
        f"- {sum(abs(float(r['abn_ret_decision_day'])) > 0.05 for r in fast_ab)} of the {len(fast_ab):,} market-hours "
        "rows with a price moved more than 5%.",
        "",
        "**The 10 best examples (largest moves among market-hours Board decisions)**",
    ]
    L += [line(r, fast=True) for r in dedupe(fast_ab, 10)]
    L += [
        "",
        "**Hand-check**",
        f'- "Material" means the patent likely covers a product that is a large share of the company\'s revenue. '
        f"It is a rule, not a reading of each patent: a patent owner with under $500M revenue, or a drug or device "
        f"company with under $2B (petitioners under $1B). {len(mat)} rows are flagged.",
        f"- All flagged rows plus a fixed random 50 of the rest ({len(chk)} rows) were checked: party name against "
        f"the company, and the outcome against a second reading of the PTAB record. {hi} agree and are marked high "
        "confidence; the rest say so in the notes.",
        "- Revenue at stake (the product's own revenue) is not filled: it needs reading each 10-K by hand.",
        "",
        "**Reproduce**",
        "- `python scripts/universe_ptab.py artifacts pdfs prices facts minutes releases` downloads (slow: the USPTO "
        "and Polygon rate limits make it hours); `python scripts/universe_ptab.py` rebuilds the CSV and this page from "
        "the cache in `data/universe/ptab/raw/`.",
        "",
        "This is historical research, not investment advice.",
    ]
    (ROOT / "docs" / "universe_ptab.md").write_text("\n".join(L) + "\n")


STAGES = {
    "artifacts": fetch_all_artifacts,
    "prices": fetch_all_prices,
    "facts": lambda: (fetch_all_facts(), fetch_all_sic()),
    "pdfs": fetch_fwd_pdfs,
}


def main() -> None:
    """python scripts/universe_ptab.py [stage ...]; no stage = build cases.csv from cache."""
    for st in sys.argv[1:]:
        if st == "minutes":
            add_minutes(build(), cached_only=False)
        elif st == "releases":
            add_releases(build(), cached_only=False)
        else:
            STAGES[st]()
    rows = build()
    add_minutes(rows)
    add_releases(rows)
    review(rows)
    write(rows)
    write_doc(rows)


if __name__ == "__main__":
    main()
