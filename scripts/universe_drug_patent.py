"""Complete list of drug-patent cases (Hatch-Waxman ANDA and BPCIA biosimilar)
decided after trial in D. Del., D.N.J. or N.D. W.Va. from 2021-01-01, plus their
Federal Circuit appeals and the cases that settled shortly before trial.

Stages (run in order; every download is cached under data/universe/drug_patent/raw/):
  mods     GovInfo USCOURTS sitemaps -> package MODS (nature of suit, parties,
           docket text of every published opinion). Keyless www.govinfo.gov pages.
  pdfs     opinion PDFs for drug-patent packages, text extracted.
  cafc     Federal Circuit opinions list (court website table) + appeal PDFs.
  build    classify opinions, join hand-checked facts (scripts/universe_drug_patent_facts.py
           is not used; facts live in data/universe/drug_patent/case_facts.csv),
           add prices, write cases.csv.

Usage: python3 scripts/universe_drug_patent.py <stage>
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "drug_patent"
RAW = OUT / "raw"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
WEB_UA = (
    f"Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36 (research; {CONTACT})"
)
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
EFTS = "https://efts.sec.gov/LATEST/search-index"
COURTS = ["ded", "njd", "wvnd"]
YEARS = range(2021, 2027)

_lock = threading.Lock()
_last: dict[str, float] = {}
GAP = {
    "ded.uscourts.gov": 0.5,
    "govinfo.gov": 0.25,
    "sec.gov": 0.15,
    "cafc.uscourts.gov": 1.0,
    "yahoo.com": 0.5,
}


def throttle(host: str) -> None:
    for key, gap in GAP.items():
        if host.endswith(key):
            with _lock:
                wait = _last.get(key, 0) + gap - time.time()
                _last[key] = max(time.time(), _last.get(key, 0) + gap)
            if wait > 0:
                time.sleep(wait)


def fetch(
    url: str, path: Path | None = None, binary: bool = False, tries: int = 4, **kw
):
    """GET with on-disk cache at `path`. Returns text/bytes, or None on failure."""
    if path is not None and path.exists():
        return path.read_bytes() if binary else path.read_text()
    host = re.sub(r"^https?://([^/]+).*", r"\1", url)
    ua = SEC_UA if host.endswith("sec.gov") else WEB_UA
    for i in range(tries):
        throttle(host)
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=60, **kw)
        except requests.RequestException:
            time.sleep(3 * (i + 1))
            continue
        if r.status_code == 200:
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
            return r.content if binary else r.text
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (i + 1))
            continue
        return None
    return None


def cache_name(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- GovInfo MODS
def packages() -> list[str]:
    ids: set[str] = set()
    for c in COURTS:
        for y in YEARS:
            p = RAW / "sitemaps" / f"{c}_{y}.xml"
            t = fetch(
                f"https://www.govinfo.gov/sitemap/USCOURTS/USCOURTS_{c}_{y}_sitemap.xml",
                p,
            )
            ids |= set(re.findall(r"/app/details/(USCOURTS-[a-z]+-[^<\s/]+)<", t or ""))
    return sorted(ids)


def parse_mods(t: str) -> dict:
    head = t.split("<relatedItem", 1)[0]

    def one(tag: str, s: str = head) -> str:
        m = re.search(rf"<{tag}[^>]*>([^<]*)</{tag}>", s)
        return m.group(1).strip() if m else ""

    parties = sorted(
        set(re.findall(r'<party fullName="([^"]*)"[^>]*role="([^"]*)"', head))
    )
    granules = []
    for g in re.findall(
        r"<relatedItem type=\"constituent\"(.*?)</relatedItem>\s*(?=<relatedItem type=\"constituent\"|</mods>)",
        t,
        re.DOTALL,
    ):
        granules.append(
            {
                "id": (
                    re.search(r"ID=\"id-([^\"]+)\"", g) or re.search("()", "")
                ).group(1),
                "date": one("dateIssued", g),
                "text": re.sub(r"\s+", " ", one("subTitle", g)),
                "pdf": (
                    re.search(r"https://www.govinfo.gov/content/pkg/[^\"<]+\.pdf", g)
                    or re.search("()", "")
                ).group(0),
            }
        )
    return {
        "title": one("title"),
        "case_number": (re.search(r"USCOURTS (\S+);", t) or re.search("()", "")).group(
            1
        ),
        "nos": one("natureSuitCode") or one("natureOfSuitCode"),
        "nos_text": one("natureSuit"),
        "cause": one("cause"),
        "parties": [{"name": n, "role": r} for n, r in parties],
        "granules": granules,
    }


def fjc_packages() -> set[str]:
    """GovInfo package IDs of the patent suits (nature of suit 830/835) in the FJC file."""
    court = {"11": "ded", "12": "njd", "24": "wvnd"}
    out = set()
    with open(OUT / "work" / "fjc_idb_patent.tsv", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["DISTRICT"] in court and r["NOS"] in ("830", "835"):
                d = r["DOCKET"].zfill(7)
                out.add(
                    f"USCOURTS-{court[r['DISTRICT']]}-{r['OFFICE']}_{d[:2]}-cv-{d[2:]}"
                )
    return out


def stage_mods(only_patent: int = 0) -> None:
    """MODS metadata for every civil package; patent suits known to the FJC file first
    (`only_patent`=1 fetches just those)."""
    pat = fjc_packages()
    ids = sorted((p for p in packages() if "-cv-" in p), key=lambda p: p not in pat)
    if only_patent:
        ids = [p for p in ids if p in pat]
    print(len(ids), "packages")
    outdir = RAW / "mods"
    outdir.mkdir(parents=True, exist_ok=True)

    def one(pid: str) -> None:
        dst = outdir / f"{pid}.json"
        if dst.exists():
            return
        t = fetch(f"https://www.govinfo.gov/metadata/pkg/{pid}/mods.xml")
        if not t:
            print("fail", pid, flush=True)
            return
        d = parse_mods(t)
        d["package"] = pid
        dst.write_text(json.dumps(d))

    done = 0
    with ThreadPoolExecutor(4) as ex:
        for _ in ex.map(one, ids):
            done += 1
            if done % 500 == 0:
                print(done, flush=True)


# ------------------------------------------------------- PDF text (cached)
def pdf_text(url: str) -> str:
    """Download a PDF (cached under raw/pdf) and return its text (cached as .txt)."""
    name = cache_name(url)
    txt = RAW / "pdf_text" / f"{name}.txt"
    if txt.exists():
        return txt.read_text()
    data = fetch(url, RAW / "pdf" / f"{name}.pdf", binary=True)
    if not data:
        return ""
    import io

    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception as e:  # noqa: BLE001 (broken PDFs are rare; keep going)
        text = f"PDF_ERROR {e}"
    txt.parent.mkdir(parents=True, exist_ok=True)
    txt.write_text(text)
    return text


PHARMA = re.compile(
    r"(?i)pharm|laborator|therapeut|biolog|bioscien|biosimilar|bioepis|biotech|biopharm|"
    r"medic|health|drug|\bteva\b|mylan|sandoz|amgen|regeneron|genentech|janssen|novartis|"
    r"pfizer|merck|lilly|astrazeneca|bayer|sanofi|abbvie|gilead|celgene|bristol|takeda|eisai|"
    r"astellas|otsuka|alkermes|amarin|vanda|jazz|avadel|exelixis|incyte|acadia|corcept|pacira|"
    r"\bpar\b|apotex|hikma|zydus|lupin|cipla|\bsun\b|aurobindo|reddy|glenmark|alembic|torrent|"
    r"\bmsn\b|hetero|natco|accord|fresenius|celltrion|coherus|alvotech|biocon|viatris|amneal|"
    r"lannett|\bendo\b|supernus|neurocrine|harmony|salix|bausch|\bucb\b|boehringer|novo|ferring|"
    r"galderma|almirall|actavis|watson|wockhardt|breckenridge|ajanta|micro labs|annora|"
    r"macleods|unichem|biogen|horizon|allergan|shire|ipsen|ionis|sarepta|vertex|alnylam|"
    r"chemo|cadila|intas|qilu|hengrui|nanjing|zhejiang|shilpa|granules|strides|camber|"
    r"orexo|indivior|insys|pernix|taro|perrigo|padagis|xiromed|slayback|eugia|alvogen|"
    r"almaject|baxter|hospira|sagent|meitheal|gland|dash|nostrum|ascend|novadoz|"
    r"\bmerz\b|galt|azurity|arbor|silvergate|eton|harrow|nevakar|exela|aspiro|qol|"
    r"\bdupont\b|tolmar|heron|liquidia|united therapeutics|esperion|cumberland|kyowa|"
    r"daiichi|chugai|mitsubishi|sumitomo|shionogi|santen|kowa|nippon|ono\b"
)
DISTRICTS = {
    "ded": r"District of Delaware",
    "njd": r"District of New Jersey",
    "wvnd": r"Northern District of West Virginia",
}


def stage_cafc() -> None:
    rows = json.loads((RAW / "cafc" / "cafc_dct.json").read_text())
    keep = []
    for date, appeal, origin, kind, link, status, path in rows:
        if date[-4:] < "2021" or kind not in ("OPINION", "RULE 36 JUDGMENT", "ORDER"):
            continue
        name = re.sub(r"<[^>]+>", "", link)
        if not PHARMA.search(name):
            continue
        keep.append(
            (date, appeal, kind, name, status, "https://www.cafc.uscourts.gov/" + path)
        )
    print(len(keep), "pharma-named Federal Circuit documents from district courts")
    out = []
    for date, appeal, kind, name, status, url in keep:
        t = pdf_text(url)
        head = re.sub(r"\s+", " ", t[:6000])
        court = next((c for c, pat in DISTRICTS.items() if re.search(pat, head)), "")
        drug = bool(
            re.search(
                r"(?i)ANDA|abbreviated new drug|271\(e\)|biosimilar|BPCIA|Hatch|505\(b\)\(2\)|Paragraph IV",
                t,
            )
        )
        dkt = re.search(r"(?i)\bNos?\.\s*((?:\d:)?\d{2}-cv-\d+[^,;.\s]*)", head)
        judge = re.search(r"(?i)(Judge|Chief Judge)\s+([A-Z][^,.]{2,40})\.", head)
        out.append(
            {
                "date": date,
                "appeal": appeal,
                "kind": kind,
                "name": name,
                "status": status,
                "url": url,
                "origin_court": court,
                "drug_terms": drug,
                "district_docket": dkt.group(1) if dkt else "",
                "district_judge": judge.group(2) if judge else "",
            }
        )
    (OUT / "work").mkdir(parents=True, exist_ok=True)
    (OUT / "work" / "cafc_candidates.json").write_text(json.dumps(out, indent=1))
    n = sum(1 for o in out if o["origin_court"] and o["drug_terms"])
    print(n, "from D. Del./D.N.J./N.D. W.Va. with drug-patent terms")


def stage_dedsite() -> None:
    """D. Del. opinions page (court website), 2021-2026, as a cross-check of GovInfo."""
    base = "https://www.ded.uscourts.gov/judges-info/opinions?field_opinion_date_value%5Bvalue%5D%5Byear%5D="
    items = []
    for y in YEARS:
        page = 0
        while True:
            t = fetch(f"{base}{y}&page={page}", RAW / "dedsite" / f"{y}_{page}.html")
            if not t:
                break
            for cap, body in re.findall(
                r'content="(\d{4}-\d\d-\d\d)T[^"]*"[^>]*>[^<]*</span></caption>(.*?)</table>',
                t,
                re.DOTALL,
            ):
                for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.DOTALL):
                    m = re.search(
                        r'views-field-title">\s*<a href="([^"]+)">([^<]*)</a>.*?views-field-field-case">\s*([^<]*?)\s*</td>.*?views-field-field-judge">\s*(?:<a[^>]*>)?([^<]*).*?href="(https://www.ded.uscourts.gov/sites/ded/files/opinions/[^"]+)"',
                        tr,
                        re.DOTALL,
                    )
                    if m:
                        items.append(
                            {
                                "date": cap,
                                "title": m.group(2).strip(),
                                "case": m.group(3).strip(),
                                "judge": m.group(4).strip(),
                                "pdf": m.group(5),
                                "page": m.group(1),
                            }
                        )
            if f"page={page + 1}" not in t.replace("&amp;", "&"):
                break
            page += 1
    (OUT / "work").mkdir(parents=True, exist_ok=True)
    (OUT / "work" / "ded_site_opinions.json").write_text(json.dumps(items, indent=0))
    print(len(items), "D. Del. website opinions")


# ------------------------------------------------- trials from the FJC database
FJC_DISTRICT = {"11": "ded", "12": "njd", "24": "wvnd"}
DRUG_NAME = re.compile(PHARMA.pattern.replace("(?i)", ""), re.IGNORECASE)


def fjc_drug() -> list[dict]:
    """FJC Integrated Database rows (official cv88on.txt) for patent suits in the three
    courts that are ANDA suits (nature of suit 835) or patent suits between drug companies."""
    import csv

    out = []
    with open(OUT / "work" / "fjc_idb_patent.tsv", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["DISTRICT"] not in FJC_DISTRICT:
                continue
            if r["NOS"] == "835" or DRUG_NAME.search(r["PLT"] + " " + r["DEF"]):
                r["court"] = FJC_DISTRICT[r["DISTRICT"]]
                r["yy"], r["num"] = r["DOCKET"][:2], int(r["DOCKET"][2:])
                out.append(r)
    return out


def us_date(s: str) -> str:
    m = re.match(r"(\d\d)/(\d\d)/(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else ""


def docket_keys(case: str) -> list[tuple[str, int]]:
    keys = []
    for part in re.split(r"[,;&]| and ", case):
        m = re.search(r"(\d\d)[- ]?(?:cv|civ)?[- ]?0*(\d{1,5})", part.replace(":", " "))
        if m:
            keys.append((m.group(1), int(m.group(2))))
    return keys


def stage_trials() -> None:
    rows = fjc_drug()
    trials = [r for r in rows if us_date(r["TRIALEND"]) >= "2020-06-01"]
    pk = {}
    for pid in packages():
        m = re.match(r"USCOURTS-([a-z]+)-\d_(\d\d)-cv-(\d{5})", pid)
        if m:
            pk[(m.group(1), m.group(2), int(m.group(3)))] = pid
    ded = {}
    for o in json.loads((OUT / "work" / "ded_site_opinions.json").read_text()):
        for k in docket_keys(o["case"]):
            ded.setdefault(k, []).append(o)
    res = []
    for r in trials:
        end = us_date(r["TRIALEND"])
        ops = []
        for o in ded.get((r["yy"], r["num"]), []) if r["court"] == "ded" else []:
            ops.append(
                {
                    "date": o["date"],
                    "label": o["title"],
                    "pdf": o["pdf"],
                    "src": "ded_site",
                }
            )
        pid = pk.get((r["court"], r["yy"], r["num"]))
        if pid:
            t = fetch(
                f"https://www.govinfo.gov/metadata/pkg/{pid}/mods.xml",
                RAW / "mods_xml" / f"{pid}.xml",
            )
            for g in parse_mods(t or "").get("granules", []):
                ops.append(
                    {
                        "date": g["date"],
                        "label": g["text"][:300],
                        "pdf": g["pdf"],
                        "src": "govinfo",
                    }
                )
        for o in ops:
            if o["date"] >= end or o["date"] >= us_date(r["TRIBEGAN"]) > "":
                txt = pdf_text(o["pdf"])
                o["head"] = re.sub(r"\s+", " ", txt[:1500])
                o["tail"] = re.sub(r"\s+", " ", txt[-1800:])
                o["pages_chars"] = len(txt)
        res.append(
            {
                k: r[k]
                for k in (
                    "court",
                    "DOCKET",
                    "OFFICE",
                    "NOS",
                    "PLT",
                    "DEF",
                    "JURY",
                    "DISP",
                    "PROCPROG",
                    "JUDGMENT",
                    "NOJ",
                )
            }
            | {
                "filed": us_date(r["FILEDATE"]),
                "trial_start": us_date(r["TRIBEGAN"]),
                "trial_end": end,
                "terminated": us_date(r["TERMDATE"]),
                "package": pid,
                "opinions": sorted(ops, key=lambda o: o["date"]),
            }
        )
    (OUT / "work" / "trials.json").write_text(json.dumps(res, indent=1))
    print(
        len(res),
        "trial dockets;",
        sum(1 for x in res if x["opinions"]),
        "with opinions found",
    )


POST_TRIAL = re.compile(
    r"(?i)bench trial|trial opinion|findings of fact and conclusions of law|"
    r"(?:following|after) a .{0,40}trial|post-trial (?:opinion|findings)"
)
ANDA = re.compile(r"ANDA|Abbreviated New Drug|biosimilar|BPCIA|271\(e\)|505\(b\)\(2\)")


def stage_scan() -> None:
    """Second discovery path, independent of the FJC trial fields: read every 2021+
    opinion in a drug-company case (D. Del. website list + GovInfo packages that are
    nature-of-suit 835 or have drug-company parties) and flag post-trial ANDA/BPCIA opinions."""
    items = []
    for o in json.loads((OUT / "work" / "ded_site_opinions.json").read_text()):
        if o["date"] >= "2021-01-01" and DRUG_NAME.search(o["title"]):
            items.append(
                {
                    "court": "ded",
                    "date": o["date"],
                    "title": o["title"],
                    "case": o["case"],
                    "pdf": o["pdf"],
                }
            )
    for f in sorted((RAW / "mods").glob("USCOURTS-*-cv-*.json")):
        d = json.loads(f.read_text())
        court = d["package"].split("-")[1]
        if court == "ded" or not (d["nos"] == "835" or DRUG_NAME.search(d["title"])):
            continue
        for g in d["granules"]:
            if g["date"] >= "2021-01-01" and g["pdf"]:
                items.append(
                    {
                        "court": court,
                        "date": g["date"],
                        "title": d["title"],
                        "case": d["case_number"],
                        "pdf": g["pdf"],
                        "label": g["text"][:200],
                    }
                )
    print(len(items), "opinions to read", flush=True)

    def one(it: dict) -> dict:
        t = pdf_text(it["pdf"])
        head = re.sub(r"\s+", " ", t[:6000])
        it["post_trial"] = bool(POST_TRIAL.search(head))
        it["anda"] = bool(ANDA.search(t))
        it["chars"] = len(t)
        return it

    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(one, items))
    (OUT / "work" / "scan.json").write_text(json.dumps(res, indent=0))
    hits = [r for r in res if r["post_trial"] and r["anda"] and r["chars"] > 15000]
    print(len(res), "read;", len(hits), "look like post-trial ANDA/BPCIA opinions")


# ------------------------------------------------------------------ build cases.csv
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
YAHOO_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REV_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
SIDE = {"win": ("good", "bad"), "loss": ("bad", "good"), "split": ("mixed", "mixed")}


def yahoo(sym: str) -> dict:
    """Daily bars {date: (adjclose, close, volume)} from the Yahoo chart API (cached)."""
    p = RAW / "yahoo" / f"{sym}.json"
    if not p.exists():
        throttle("yahoo.com")
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?period1=1514764800&period2={int(time.time())}&interval=1d"
        r = requests.get(url, headers={"User-Agent": YAHOO_UA}, timeout=60)
        if r.status_code != 200 or not r.text.startswith("{"):
            print("yahoo failed", sym, r.status_code)
            return {}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(r.text)
    try:
        res = json.loads(p.read_text())["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    except (KeyError, TypeError, IndexError, json.JSONDecodeError):
        return {}
    out = {}
    for ts, a, c, v in zip(res["timestamp"], adj, q["close"], q["volume"]):
        if a is not None and c is not None:
            out[time.strftime("%Y-%m-%d", time.gmtime(ts - 5 * 3600))] = (a, c, v or 0)
    return out


def event_returns(bars: dict, bench: dict, day: str, two_day: bool) -> dict:
    days = sorted(bars)
    i = next((k for k, d in enumerate(days) if d >= day), None)
    if not day or i is None or i == 0 or i + 1 >= len(days):
        return {}
    j = min(i + 1 if two_day else i, len(days) - 1)

    def ret(src: dict, a: int, b: int) -> float | None:
        try:
            return src[days[b]][0] / src[days[a]][0] - 1
        except KeyError:
            return None

    r, rb = ret(bars, i - 1, j), ret(bench, i - 1, j)
    p5 = ret(bars, i - 1, min(i + 4, len(days) - 1))
    adv = [bars[d][1] * bars[d][2] for d in days[max(0, i - 20) : i]]
    return {
        "ret": r,
        "abn": None if r is None or rb is None else r - rb,
        "plus5": p5,
        "adv": sum(adv) / len(adv) if adv else None,
        "close_end": bars[days[j]][1],
        "end_day": days[j],
        "trade_day": days[i],
        "close_before": bars[days[i - 1]][1],
    }


def sec_json(kind: str, cik: int) -> dict:
    url = f"https://data.sec.gov/{kind}/CIK{cik:010d}.json"
    t = fetch(url, RAW / "sec" / f"{kind.replace('/', '_')}_{cik}.json")
    return json.loads(t) if t else {}


def cik_map() -> dict:
    t = fetch(
        "https://www.sec.gov/files/company_tickers.json",
        RAW / "sec" / "company_tickers.json",
    )
    m = {v["ticker"]: (int(v["cik_str"]), v["title"]) for v in json.loads(t).values()}
    m.update(MANUAL_CIK)
    return m


# Delisted or renamed tickers missing from SEC's current ticker list (checked on EDGAR).
MANUAL_CIK: dict = {
    "AVDL": (1012477, "Avadel Pharmaceuticals plc"),
    "FOLD": (1178879, "Amicus Therapeutics, Inc."),
    "ENDP": (1593034, "Endo International plc"),
    "BDSI": (1103021, "BioDelivery Sciences International, Inc."),
}

# Product sales read by hand from the annual report text where the XBRL has no product tag.
TEXT = "10-K/20-F text, read by hand"
MANUAL_STAKE: dict = {
    "ded:20-430": {
        "value": 1_644e6,
        "fy_end": "2021-12-31",
        "us_only": False,
        "src": TEXT,
        "accession": "0000885590-22-000010",
        "filed": "2022-02-23",
    },
    "wvnd:19-201": {
        "value": 4_644e6,
        "fy_end": "2022-12-31",
        "us_only": False,
        "src": TEXT,
        "accession": "0001370368-23-000006",
        "filed": "2023-02-01",
    },
    "njd:20-13103": {
        "value": 2_714e6,
        "fy_end": "2023-01-01",
        "us_only": True,
        "src": TEXT,
        "accession": "0000200406-23-000016",
        "filed": "2023-02-16",
    },
    "njd:18-3632": {
        "value": 401_858e3,
        "fy_end": "2022-12-31",
        "us_only": True,
        "src": TEXT,
        "accession": "0001628280-23-005581",
        "filed": "2023-02-28",
        "company_total": 401_858e3,
        "caveat": "Corcept's whole net product revenue; Korlym is the only "
        "product its 10-K says it sells (in the US).",
    },
    "njd:21-6964": {
        "value": 261_221e3,
        "fy_end": "2022-12-31",
        "us_only": False,
        "src": TEXT,
        "accession": "0001356576-23-000016",
        "filed": "2023-03-09",
    },
}
# Opinions posted under seal whose result still reached the market the same session.
SEALED_BUT_PUBLIC = {
    "njd:21-19829": (
        "2024-08-09 15:17",
        (
            "The opinion (docket entry 403) was posted under seal at 15:17 ET, yet the stock "
            "closed 48% lower that day (22.36 to 11.70), so the result was public by the "
            "16:00 close; first_public_time_et is the posting minute, precision hour."
        ),
    ),
}
JNJ_INVEGA = (
    "J&J reports Invega Sustenna/Xeplion and Invega Trinza/Trevicta as one combined sales "
    "line, so this is the whole paliperidone long-acting franchise, not one product."
)


def fact_before(
    facts: dict, ns: str, tags: list[str], day: str, annual: bool
) -> float | None:
    best = None
    for tag in tags:
        for unit in (
            facts.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {}).values()
        ):
            for f in unit:
                if f.get("filed", "9") > day or (
                    annual and (f.get("fp") != "FY" or not f.get("start"))
                ):
                    continue
                if annual and not (330 <= (_d(f["end"]) - _d(f["start"])) <= 380):
                    continue
                if best is None or (f["end"], f["filed"]) > (
                    best["end"],
                    best["filed"],
                ):
                    best = f
    return best["val"] if best else None


def _d(s: str) -> int:
    return int(time.mktime(time.strptime(s[:10], "%Y-%m-%d")) // 86400)


def utc_to_et(iso: str) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    t = datetime.fromisoformat(iso)
    return t.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")


def company_release(cik: int, day: str) -> str:
    """Acceptance time (ET) of the company's first 8-K or 6-K filed on the decision day or the next two days."""
    sub = sec_json("submissions", cik).get("filings", {}).get("recent", {})
    best = ""
    cols = (
        "form",
        "filingDate",
        "acceptanceDateTime",
        "accessionNumber",
        "primaryDocument",
    )
    for form, fd, acc, num, doc in zip(*(sub.get(c, []) for c in cols)):
        if form in ("8-K", "6-K") and day <= fd and _d(fd) - _d(day) <= 2:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{num.replace('-', '')}/{doc}"
            text = fetch(url, RAW / "sec" / "filings" / f"{num}.htm") or ""
            text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
            # Only the filing's own news (from the first Item to the exhibits list), not
            # the risk-factor boilerplate, which mentions patents in every 8-K.
            m = re.search(
                r"Item \d\.\d\d(.*?)(Item 9\.01|SIGNATURE|Forward-Looking)",
                text,
                re.DOTALL | re.IGNORECASE,
            )
            news = m.group(1) if m else text[:6000]
            if not re.search(
                r"(?i)district court|court ruled|court's decision|ruling|trial opinion|"
                r"patent litigation|ANDA|biosimilar",
                news,
            ):
                continue
            t = utc_to_et(acc)
            best = min(best, t) if best else t
    return best


def stage_build() -> None:
    import csv

    fjc = {(r["court"], r["yy"], r["num"]): r for r in fjc_drug()}
    groups: dict = {}
    for r in fjc.values():
        groups.setdefault(
            (r["court"], r["PLT"][:10].upper(), us_date(r["TRIALEND"])), []
        ).append(r)
    trials = {
        (t["court"], t["DOCKET"]): t
        for t in json.loads((OUT / "work" / "trials.json").read_text())
    }
    pk = {}
    for pid in packages():
        m = re.match(r"USCOURTS-([a-z]+)-\d_(\d\d)-cv-(\d{5})", pid)
        if m:
            pk[(m.group(1), m.group(2), int(m.group(3)))] = pid
    ciks = cik_map()
    bench = yahoo("XBI")
    cl_ids = {
        k: v["cl"]
        for k, v in json.loads((OUT / "work" / "cl_targets.json").read_text())
    }
    today = time.strftime("%Y-%m-%d")
    two_years_ago = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 730 * 86400))
    rows = []
    with open(OUT / "work" / "case_facts.csv", newline="") as fh:
        facts_rows = list(csv.DictReader(fh))
    for f in facts_rows:
        if f["status"] == "exclude":
            continue
        court, dk = f["key"].split(":")
        yy, num = dk.split("-")
        r = fjc.get((court, yy, int(num)))
        if r is None:
            print("no FJC row", f["key"])
            continue
        mates = (
            groups.get((court, r["PLT"][:10].upper(), us_date(r["TRIALEND"])), [r])
            if f["outcome"] not in ("settled", "dismissed")
            else [r]
        )
        dockets = sorted({f"{m['yy']}-{m['num']}" for m in mates})
        filed = min(us_date(m["FILEDATE"]) for m in mates)
        decision = f["decision_date"] or us_date(r["TERMDATE"])
        src = ""
        for m in mates:
            for o in trials.get((court, m["DOCKET"]), {}).get("opinions", []):
                if o["date"] == decision and (not src or o["src"] == "ded_site"):
                    src = o["pdf"]
        pid = pk.get((court, yy, int(num)))
        docket_url = f"https://www.govinfo.gov/app/details/{pid}" if pid else ""
        if f["outcome"] in ("settled", "dismissed"):
            src = src or "FJC Integrated Database termination date"
        jury = r["JURY"] in ("P", "D", "B") and r["DISP"] == "7"
        known = "yes" if jury or re.search(r"(?i)jury verdict", f["notes"]) else "no"
        base = {
            "case_id": f"drug_patent-{court}-{dk}",
            "case_type": "drug_patent",
            "case_name": f["case_name"],
            "court": court,
            "docket_number": "; ".join(dockets),
            "docket_url": docket_url,
            "filed_date": filed,
            "trial_start_date": us_date(r["TRIBEGAN"]),
            "trial_end_date": us_date(r["TRIALEND"]),
            "decision_date": decision,
            "decision_time_et": "",
            "decision_known_in_advance": known,
            "decision_source_url": src,
            "outcome": f["outcome"],
            "confidence": f["confidence"],
            "days_filed_to_decision": (_d(decision) - _d(filed))
            if decision and filed
            else "",
            "sources": "FJC Integrated Database (fjc.gov cv88on); "
            + ("GovInfo USCOURTS; " if pid else "")
            + "court opinion PDF",
            "first_public_source": "court docket (CM/ECF)"
            if f["outcome"] not in ("settled", "dismissed")
            else "court docket (CM/ECF) or company release",
            "first_public_time_et": decision,
            "time_precision": "day",
            "during_market_hours": "unknown",
        }
        notes = [f["notes"]] if f["notes"] else []
        if f["drug"]:
            notes.append(f"Drug: {f['drug']}.")
        parties = [(t, "brand") for t in f["brand_tickers"].split(";") if t] + [
            (t, "challenger") for t in f["challenger_tickers"].split(";") if t
        ]
        if not parties:
            rows.append(
                base
                | {
                    "notes": " ".join(
                        notes
                        + ["No US-listed party; kept so the case list is complete."]
                    ),
                    "minute_data_available": "no",
                }
            )
            continue
        for tkr, role in parties:
            other = [t for t, rl in parties if rl != role]
            row = dict(
                base,
                ticker=tkr,
                company_role=role,
                counterparty=r["DEF"].title() if role == "brand" else r["PLT"].title(),
                counterparty_ticker=";".join(other),
            )
            n = list(notes)
            if f["outcome"] in SIDE:
                row["outcome_for_company"] = SIDE[f["outcome"]][
                    0 if role == "brand" else 1
                ]
            else:
                row["outcome_for_company"] = "unknown"
            cik, title = ciks.get(tkr, (None, ""))
            row["company"] = title
            bars = yahoo(tkr)
            if not bars:
                n.append(f"No Yahoo price history for {tkr} (delisted or renamed).")
            t_cl, cl_desc = cl_entry_time(
                cl_ids.get(base["case_id"], []), decision, f["notes"]
            )
            if t_cl:
                row["decision_time_et"] = t_cl[11:]
                row["first_public_source"] = (
                    "court docket (CM/ECF entry time via CourtListener RECAP)"
                )
                row["first_public_time_et"], row["time_precision"] = t_cl, "minute"
                n.append(f"Docket entry: {cl_desc}.")
            if not t_cl and f["key"] in SEALED_BUT_PUBLIC:
                t_cl, why = SEALED_BUT_PUBLIC[f["key"]]
                row["decision_time_et"] = t_cl[11:]
                row["first_public_source"] = (
                    "court docket (opinion posted under seal; result out before the close)"
                )
                row["first_public_time_et"], row["time_precision"] = t_cl, "hour"
                n.append(why)
            known_time = bool(t_cl) and market_hours(t_cl) == "yes"
            ev_day = decision if known_time or not t_cl else shift(decision, 1)
            ev = event_returns(bars, bench, ev_day, two_day=not t_cl) if bars else {}
            fe = event_returns(bars, bench, filed, two_day=True) if bars else {}
            row["ret_decision_day"], row["abn_ret_decision_day"] = (
                ev.get("ret"),
                ev.get("abn"),
            )
            row["ret_decision_plus5"], row["adv_usd_20d_before_decision"] = (
                ev.get("plus5"),
                ev.get("adv"),
            )
            row["ret_filing_day"], row["abn_ret_filing_day"] = (
                fe.get("ret"),
                fe.get("abn"),
            )
            if ev and not t_cl:
                n.append(
                    "Decision time of day unknown, so the decision return is 2-day "
                    "(event day plus next), benchmark XBI."
                )
            if fe:
                n.append("Filing-day return is 2-day (complaint filing time unknown).")
            recent = two_years_ago <= decision <= today and bool(bars)
            unrelated = re.findall(r"Price move unrelated: ([A-Z;]+)", f["notes"])
            big = (
                ev
                and abs(ev.get("abn") or 0) >= 0.03
                and tkr not in ";".join(unrelated).split(";")
            )
            win = (
                decision,
                ev.get("trade_day"),
                ev.get("end_day"),
                ev.get("close_before"),
            )
            if recent and big and not t_cl:
                pj = price_jump(tkr, *win, ev["close_end"])
                if pj.get("jump"):
                    row["first_public_source"] = (
                        "court docket (posting minute inferred from first price jump)"
                    )
                    row["first_public_time_et"] = pj["jump"]
                    row["time_precision"] = "inferred from price"
                    if pj["jump"][11:] in ("09:30", "09:31"):
                        n.append(
                            "Stock gapped at the open, so the outcome was public before 09:30 "
                            "(first_public_time_et is the open, an upper bound)."
                        )
            first = row.get("first_public_time_et", "")
            if len(first) == 16:
                gap = row["time_precision"] == "inferred from price" and first[11:] in (
                    "09:30",
                    "09:31",
                )
                row["during_market_hours"] = "no" if gap else market_hours(first)
                if recent and big and not gap:
                    pj = price_jump(tkr, *win, ev["close_end"], after=first)
                    if pj.get("half"):
                        row["minutes_to_half_move"] = minutes_between(first, pj["half"])
            if cik:
                facts = sec_json("api/xbrl/companyfacts", cik)
                shares = fact_before(
                    facts, "dei", ["EntityCommonStockSharesOutstanding"], filed, False
                )
                if shares and fe.get("close_before"):
                    row["market_cap_usd_at_filing"] = round(shares * fe["close_before"])
                rev = fact_before(facts, "us-gaap", REV_TAGS, filed, True)
                if rev:
                    row["revenue_ttm_usd_at_filing"] = rev
                elif facts:
                    n.append(
                        "No US-GAAP revenue tag before filing (foreign filer or pre-revenue)."
                    )
                rel = company_release(cik, decision)
                row["company_release_time_et"] = rel
                first = row.get("first_public_time_et", "")
                if (
                    rel
                    and row.get("time_precision") == "inferred from price"
                    and rel < first
                ):
                    if isinstance(row.get("minutes_to_half_move"), int):
                        row["minutes_to_half_move"] += minutes_between(rel, first)
                    row["first_public_source"] = (
                        "company 8-K (came before the price jump)"
                    )
                    row["first_public_time_et"], row["time_precision"] = rel, "minute"
                    row["during_market_hours"] = market_hours(rel)
                    first = rel
                if rel and len(first) == 16:
                    row["lead_minutes_vs_company_release"] = minutes_between(first, rel)
            row["minute_data_available"] = (
                "yes"
                if decision >= two_years_ago and decision <= today and bars
                else "no"
            )
            brand_t = [t for t, rl in parties if rl == "brand"]
            stake = {}
            if f["key"] in MANUAL_STAKE:
                stake = MANUAL_STAKE[f["key"]]
            elif f["drug"] and brand_t and brand_t[0] in ciks:
                stake = product_revenue(
                    ciks[brand_t[0]][0], f["drug"], decision or today
                )
            if stake.get("value"):
                row["revenue_at_stake_usd"] = round(stake["value"])
                where = "US" if stake["us_only"] else "worldwide (no US split given)"
                src = stake.get("src", "10-K/20-F XBRL")
                n.append(
                    f"Revenue at stake: {brand_t[0]} {f['drug']} {where} sales, fiscal year "
                    f"ending {stake['fy_end']} ({src}, accession {stake['accession']})."
                )
                if stake.get("caveat"):
                    n.append(stake["caveat"])
                if brand_t[0] == "JNJ" and "invega" in f["drug"].lower():
                    n.append(JNJ_INVEGA)
                if row["ticker"] == brand_t[0] and stake.get("company_total"):
                    row["revenue_at_stake_share"] = round(
                        stake["value"] / stake["company_total"], 4
                    )
            elif stake.get("currency"):
                n.append(
                    f"Revenue at stake blank: the brand tags {f['drug']} sales only in "
                    f"{stake['currency']}, not US dollars."
                )
            elif not f["drug"] or not brand_t:
                n.append(
                    "Revenue at stake blank: brand not US-listed or drug not identified."
                )
            else:
                n.append(
                    "Revenue at stake blank: product sales not tagged in the brand's XBRL."
                )
            row["notes"] = " ".join(n)
            rows.append(row)
    rows += appeal_rows(rows, bench, ciks)
    with open(OUT / "cases.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(
                {
                    k: (f"{v:.4f}" if isinstance(v, float) and abs(v) < 10 else v)
                    for k, v in row.items()
                    if k in COLUMNS
                }
            )
    print(len(rows), "rows written")


# ------------------------------------------------------------------ posting times
CL_API = "https://www.courtlistener.com/api/rest/v4/docket-entries/"
CL_DIR = RAW / "courtlistener"


def shift(day: str, n: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime((_d(day) + n) * 86400))


def stage_settle_edgar() -> None:
    """Scheduled trial dates for the settled/dismissed candidates, from the listed party's own
    10-K/10-Q/20-F/6-K text in the 400 days before the case ended (EDGAR full-text search)."""
    from datetime import datetime, timedelta

    cache = RAW / "sec" / "fts"
    cache.mkdir(parents=True, exist_ok=True)

    def get(url: str, params: dict | None, name: str) -> str:
        p = cache / name
        if p.exists():
            return p.read_text()
        throttle("sec.gov")
        r = requests.get(url, params=params, headers={"User-Agent": SEC_UA}, timeout=60)
        if r.status_code != 200:
            return ""
        p.write_text(r.text)
        return r.text

    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    when = rf"(?:{months})\s+(?:\d{{1,2}},\s+)?20\d\d"
    ciks = cik_map()
    out = []
    for x in json.loads((OUT / "work" / "settle_candidates.json").read_text()):
        tkr = x["brand"] or x["chal"]
        if not tkr or x["months"] < 24 or tkr not in ciks:
            continue
        cik = ciks[tkr][0]
        other = x["dfn"] if x["brand"] else x["plt"]
        word = re.sub(r"[^A-Za-z]", "", other.split()[0]).title()
        end = datetime.fromisoformat(x["term"])
        q = {
            "q": f'"{word}" trial',
            "forms": "10-K,10-Q,20-F,6-K",
            "dateRange": "custom",
            "ciks": f"{cik:010d}",
            "startdt": (end - timedelta(days=400)).strftime("%Y-%m-%d"),
            "enddt": x["term"],
        }
        j = get(EFTS, q, f"fts_{cik}_{word}_{x['term']}.json")
        hits = json.loads(j)["hits"]["hits"] if j else []
        found = set()
        for h in hits[:3]:
            acc, fn = h["_id"].split(":")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{fn}"
            txt = re.sub(
                r"<[^>]+>|&#\d+;|&nbsp;", " ", get(url, None, f"doc_{acc}_{fn}")
            )
            for sent in re.split(r"(?<=\.)\s", re.sub(r"\s+", " ", txt)):
                if word.lower() not in sent.lower() or not re.search(
                    r"\btrial\b", sent, re.IGNORECASE
                ):
                    continue
                if not re.search(
                    r"schedul|set for|begin|commence", sent, re.IGNORECASE
                ):
                    continue
                for d in re.findall(when, sent):
                    d = re.sub(r"\s+", " ", d)
                    dd = datetime.strptime(d, "%B %d, %Y" if "," in d else "%B %Y")
                    if dd >= end - timedelta(days=30):
                        found.add(
                            (
                                dd.strftime("%Y-%m-%d"),
                                h["_source"]["file_date"],
                                url,
                                sent[:300],
                            )
                        )
        trial = min((f[0] for f in found if f[0] >= x["term"][:8] + "01"), default="")
        out.append(
            x
            | {
                "edgar_trial": sorted(found),
                "trial_scheduled": trial,
                "days_before_trial": max(0, (datetime.fromisoformat(trial) - end).days)
                if trial
                else "",
            }
        )
    (OUT / "work" / "settle_edgar.json").write_text(json.dumps(out, indent=1))
    hit = [x for x in out if x["trial_scheduled"]]
    near = [x for x in hit if x["days_before_trial"] <= 90]
    print(
        len(out),
        "checked;",
        len(hit),
        "with a stated trial date;",
        len(near),
        "within 90 days",
    )


def stage_settlecheck(budget: int = 15) -> None:
    """Docket entries in the 200 days before each settled listed-party ANDA case ended, newest
    first, to find a scheduled trial date. At most `budget` CourtListener requests per run."""
    CL_DIR.mkdir(parents=True, exist_ok=True)
    tok = os.environ.get("COURTLISTENER_API_TOKEN", "")
    cand = {
        x["court"] + ":" + x["docket"]: x
        for x in json.loads((OUT / "work" / "settle_candidates.json").read_text())
    }
    targets = json.loads((OUT / "work" / "settle_cl_targets.json").read_text())
    used = 0
    for key in _settle_open():
        lo, hi = shift(cand[key]["term"], -200), cand[key]["term"]
        for cid in targets[key][:1]:
            p = CL_DIR / f"entries_{cid}_{lo}_{hi}.json"
            if p.exists():
                continue
            if used >= budget:
                print("budget used:", used)
                return
            throttle("courtlistener.com")
            time.sleep(30)  # 5 requests/minute, shared with other sessions
            r = requests.get(
                CL_API,
                params={
                    "docket": cid,
                    "date_filed__gte": lo,
                    "date_filed__lte": hi,
                    "order_by": "-date_filed",
                },
                headers={"Authorization": f"Token {tok}", "User-Agent": SEC_UA},
                timeout=90,
            )
            used += 1
            if r.status_code == 429:
                print("CourtListener 429:", r.json().get("detail", ""))
                return
            if r.status_code == 200:
                p.write_text(r.text)
                print(key, cid, len(r.json().get("results", [])), "entries")
            else:
                print(key, cid, "HTTP", r.status_code)
    print("all settlement targets fetched; used", used)


CL_SEARCH = "https://www.courtlistener.com/api/rest/v4/search/"
SETTLE_TERMS = (
    'description:("trial set" OR "trial reset" OR "trial scheduled" OR "trial is scheduled"'
    ' OR "trial date" OR "trial rescheduled" OR "trial held" OR "trial completed"'
    ' OR "pretrial conference set" OR "pretrial order")'
)


def _settle_open() -> list[str]:
    """Settlement candidates that are not already trial-universe cases, newest end date first."""
    cand = {
        x["court"] + ":" + x["docket"]: x
        for x in json.loads((OUT / "work" / "settle_candidates.json").read_text())
    }
    with open(OUT / "cases.csv", newline="") as f:
        ids = {r["case_id"] for r in csv.DictReader(f)}
    targets = json.loads((OUT / "work" / "settle_cl_targets.json").read_text())

    def cid(k: str) -> str:
        c, d = k.split(":")
        a, b = d.split("-")
        return f"drug_patent-{c}-{int(a)}-{int(b)}"

    keys = [k for k in targets if targets[k] and cid(k) not in ids]
    return sorted(keys, key=lambda k: cand[k]["term"], reverse=True)


def _settle_batches() -> list[tuple[str, list[str], Path]]:
    targets = json.loads((OUT / "work" / "settle_cl_targets.json").read_text())
    keys = _settle_open()
    out = []
    for i in range(0, len(keys), 10):
        batch = keys[i : i + 10]
        q = (
            "docket_id:("
            + " OR ".join(str(targets[k][0]) for k in batch)
            + ") AND "
            + SETTLE_TERMS
        )
        out.append(
            (
                q,
                batch,
                CL_DIR
                / f"search_settle_{hashlib.sha1(q.encode()).hexdigest()[:12]}.json",
            )
        )
    return out


def stage_settlesearch(budget: int = 15) -> None:
    """One CourtListener search per 10 open settlement candidates: every docket entry, over the
    whole docket, whose text sets, moves or records a trial or a pretrial conference/order.
    Prints how many requests were used on its last line."""
    CL_DIR.mkdir(parents=True, exist_ok=True)
    tok = os.environ.get("COURTLISTENER_API_TOKEN", "")
    used = 0
    for q, batch, p in _settle_batches():
        if p.exists():
            continue
        if used >= budget:
            break
        throttle("courtlistener.com")
        time.sleep(30)
        r = requests.get(
            CL_SEARCH,
            params={"type": "r", "q": q},
            headers={"Authorization": f"Token {tok}", "User-Agent": SEC_UA},
            timeout=120,
        )
        used += 1
        if r.status_code == 429:
            print("CourtListener 429:", r.json().get("detail", ""))
            break
        if r.status_code != 200:
            print("search HTTP", r.status_code)
            continue
        p.write_text(json.dumps({"q": q, "batch": batch, "resp": r.json()}))
        res = r.json().get("results", [])
        print(len(batch), "dockets searched;", len(res), "with trial entries")
    print("settlement search used", used)


def stage_settledocket() -> None:
    """Scheduled trial dates for the settlement candidates, from the cached docket entries
    (stage_settlecheck) and docket searches (stage_settlesearch): flags candidates that ended
    within 90 days before a trial date set on the docket, or after a pretrial order or trial."""
    from datetime import date, datetime

    cand = {
        x["court"] + ":" + x["docket"]: x
        for x in json.loads((OUT / "work" / "settle_candidates.json").read_text())
    }
    targets = json.loads((OUT / "work" / "settle_cl_targets.json").read_text())
    open_keys = set(_settle_open())
    texts: dict[str, list[tuple[str, str]]] = {}
    searched: set[str] = set()
    for _, batch, p in _settle_batches():
        if not p.exists():
            continue
        searched.update(batch)
        by_id = {str(targets[k][0]): k for k in batch}
        for d in json.loads(p.read_text())["resp"].get("results", []):
            k = by_id.get(str(d.get("docket_id")))
            for e in d.get("recap_documents", []) if k else []:
                desc = e.get("description") or e.get("short_description") or ""
                texts.setdefault(k, []).append((e.get("entry_date_filed") or "", desc))
    fetched: set[str] = set()
    for key, ids in targets.items():
        lo, hi = shift(cand[key]["term"], -200), cand[key]["term"]
        p = CL_DIR / f"entries_{ids[0]}_{lo}_{hi}.json" if ids else None
        if p and p.exists():
            fetched.add(key)
            for e in json.loads(p.read_text()).get("results", []):
                desc = e.get("description") or " | ".join(
                    d.get("description") or "" for d in e.get("recap_documents", [])
                )
                texts.setdefault(key, []).append((e.get("date_filed") or "", desc))
    md = r"(\d{1,2})/(\d{1,2})/(20\d\d)"
    set_re = re.compile(
        r"(?i)(?<!pre)\b(bench trial|jury trial|trial)\b[^.|]{0,80}?\b(?:set|reset|scheduled|rescheduled)\b"
        r"[^.|]{0,40}?(?:for|to begin|to start|on)\s+" + md
    )
    held_re = re.compile(r"(?i)\btrial (?:held|completed|begun|began)\b")
    pto_re = re.compile(
        r"(?i)\b(?:proposed )?pretrial order\b|pretrial conference held"
    )
    out = []
    for key in targets:
        x = cand[key]
        if key not in open_keys:
            out.append(x | {"docket_checked": False, "in_trial_universe": True})
            continue
        if key not in searched and key not in fetched:
            out.append(x | {"docket_checked": False})
            continue
        found, held, pto = set(), [], []
        for filed, desc in texts.get(key, []):
            for m in set_re.finditer(desc):
                try:
                    d = date(int(m[4]), int(m[2]), int(m[3])).isoformat()
                except ValueError:
                    continue
                found.add((d, filed, desc[:300]))
            if held_re.search(desc):
                held.append((filed, desc[:300]))
            if pto_re.search(desc) and filed <= x["term"]:
                pto.append((filed, desc[:300]))
        later = sorted(f for f in found if f[0] >= x["term"] and f[1] <= x["term"])
        trial = later[0][0] if later else ""
        days = (
            (datetime.fromisoformat(trial) - datetime.fromisoformat(x["term"])).days
            if trial
            else ""
        )
        out.append(
            x
            | {
                "docket_checked": True,
                "searched": key in searched,
                "entries_fetched": key in fetched,
                "docket_trial_dates": sorted(found),
                "trial_scheduled": trial,
                "days_before_trial": days,
                "trial_held_entries": sorted(set(held)),
                "pretrial_order_entries": sorted(set(pto))[-3:],
            }
        )
    (OUT / "work" / "settle_docket.json").write_text(json.dumps(out, indent=1))
    chk = [x for x in out if x["docket_checked"]]
    hit = [x for x in chk if x["trial_scheduled"]]
    near = [x for x in hit if x["days_before_trial"] <= 90]
    print(
        len(out),
        "candidates;",
        len(open_keys),
        "not already trial cases;",
        len(chk),
        "checked;",
        len(hit),
        "with a later trial date on the docket;",
        sum(1 for x in chk if x["pretrial_order_entries"]),
        "with a pretrial order;",
        sum(1 for x in chk if x["trial_held_entries"]),
        "with a trial held",
    )
    print(len(near), "ended within 90 days before trial:")
    for x in near:
        print(
            " ",
            x["court"],
            x["docket"],
            x["term"],
            "trial",
            x["trial_scheduled"],
            x["plt"][:30],
            "v.",
            x["dfn"][:30],
        )
    for x in chk:
        if (x["pretrial_order_entries"] or x["trial_held_entries"]) and x not in near:
            print(
                "  check:",
                x["court"],
                x["docket"],
                x["term"],
                x["plt"][:30],
                "v.",
                x["dfn"][:30],
            )


def stage_cltimes(budget: int = 15) -> None:
    """Docket entries around each listed case's decision date, newest case first.
    Spends at most `budget` CourtListener API requests per run and stops at the first 429."""
    CL_DIR.mkdir(parents=True, exist_ok=True)
    tok = os.environ.get("COURTLISTENER_API_TOKEN", "")
    used = 0
    for case_id, t in json.loads((OUT / "work" / "cl_targets.json").read_text()):
        if not t["decision_date"]:
            continue
        word = re.sub(r"[^a-z]", "", case_id.split("-")[0])
        ids = (
            t["cl"]
            if len(t["cl"]) == 1
            else [c for c in t["cl"] if word and word in c["slug"]] or t["cl"][:1]
        )
        lo, hi = shift(t["decision_date"], -2), shift(t["decision_date"], 3)
        for c in ids:
            p = CL_DIR / f"entries_{c['id']}_{lo}_{hi}.json"
            if p.exists():
                continue
            if used >= budget:
                print("budget used:", used)
                return
            throttle("courtlistener.com")
            time.sleep(30)  # 5 requests/minute, shared with other sessions
            r = requests.get(
                CL_API,
                params={
                    "docket": c["id"],
                    "date_filed__gte": lo,
                    "date_filed__lte": hi,
                },
                headers={"Authorization": f"Token {tok}", "User-Agent": SEC_UA},
                timeout=90,
            )
            used += 1
            if r.status_code == 429:
                print("CourtListener 429:", r.json().get("detail", ""))
                return
            if r.status_code == 200:
                p.write_text(r.text)
                print(case_id, c["id"], len(r.json().get("results", [])), "entries")
            else:
                print(case_id, c["id"], "HTTP", r.status_code)
    print("all targets fetched; used", used)


def polygon_day(sym: str, day: str) -> list:
    """1-minute bars for one day from Polygon (free key: about 2 years back, 5 requests/minute,
    shared with other sessions, so wait and retry when it says the per-minute limit is hit)."""
    p = RAW / "polygon" / f"{sym}_{day}.json"
    key = os.environ.get("POLYGON_API_KEY", "")
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/{day}/{day}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={key}"
    )
    for wait in (20, 65, 65, 120):
        if p.exists():
            break
        time.sleep(wait)
        r = requests.get(url, timeout=60)
        try:
            j = r.json()
        except ValueError:
            j = {}
        if j.get("status") in ("OK", "DELAYED") and j.get("results"):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(r.text)
        elif "maximum requests" not in (j.get("error") or ""):
            print(
                "polygon",
                sym,
                day,
                j.get("status"),
                (j.get("error") or j.get("message") or "")[:60],
            )
            return []
    return json.loads(p.read_text()).get("results", []) if p.exists() else []


def et_minute(ms: int) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(ms / 1000, ZoneInfo("America/New_York")).strftime(
        "%Y-%m-%d %H:%M"
    )


def price_jump(
    sym: str,
    start: str,
    trade_day: str,
    end_day: str,
    ref: float,
    close: float,
    after: str = "",
) -> dict:
    """First minute (from `after`, or 09:30 on `start`) when the stock had made a third of its move
    from `ref` (prior close) to `close` (event-day close), and the first minute it had made half."""
    move = close / ref - 1
    bars = []
    for day in sorted({start, trade_day, end_day}):
        bars += polygon_day(sym, day)
    out = {}
    begin = after or f"{start} 00:00"
    for b in bars:
        t = et_minute(b["t"])
        if t < begin or t > f"{end_day} 16:00":
            continue
        got = (b["c"] / ref - 1) / move
        if "jump" not in out and got >= 1 / 3:
            out["jump"] = t
        if got >= 0.5:
            out["half"] = t
            break
    return out


def minutes_between(a: str, b: str) -> int:
    ta = time.mktime(time.strptime(a, "%Y-%m-%d %H:%M"))
    tb = time.mktime(time.strptime(b, "%Y-%m-%d %H:%M"))
    return round((tb - ta) / 60)


def market_hours(t: str) -> str:
    if len(t) < 16:
        return "unknown"
    wd = time.strptime(t[:10], "%Y-%m-%d").tm_wday
    return "yes" if wd < 5 and "09:30" <= t[11:] < "16:00" else "no"


def cl_entry_time(
    case_ids: list, decision: str, facts_note: str = ""
) -> tuple[str, str]:
    """(time ET 'YYYY-MM-DD HH:MM', description) of the decision's docket entry, from cached CourtListener data."""
    best = ("", "")
    for c in case_ids:
        for p in CL_DIR.glob(f"entries_{c['id']}_*.json"):
            for e in json.loads(p.read_text()).get("results", []):
                desc = e.get("description") or ""
                for d in e.get("recap_documents") or []:
                    desc = desc or d.get("description") or ""
                if e.get("date_filed") != decision or not re.search(
                    r"(?i)opinion|findings of fact|judgment|memorandum order|verdict|stipulat|dismiss"
                    r"|^ORDER\b.*\b(infring\w*|(in)?valid)\b",
                    desc,
                ):
                    continue
                if re.search(
                    r"(?i)^ORDER directing [^.]*submit",
                    desc,
                ):
                    continue  # asks the parties for a judgment; does not say who won
                if re.search(r"(?i)\b(un)?sealed\b|under seal", desc):
                    continue  # posted under seal, so the outcome was not public at that minute
                if re.search(
                    r"(?i)temporar\w* seal|sealed (opinion|findings)", facts_note
                ) and (re.search(r"(?i)opinion|findings of fact", desc)):
                    continue  # the opinion entry itself was sealed when posted
                if e.get("time_filed"):
                    t = f"{e['date_filed']} {e['time_filed'][:5]}"
                    if not best[0] or t < best[0]:
                        best = (t, desc[:120])
    return best


# ------------------------------------------------------------------ revenue at stake
def annual_reports(cik: int, before: str) -> list[tuple[str, str]]:
    """(accession, filing date) of the company's 10-K / 20-F filings before `before`, newest first."""
    filings = sec_json("submissions", cik).get("filings", {})
    pages = [filings.get("recent", {})]
    for f in filings.get("files", []):
        t = fetch(
            f"https://data.sec.gov/submissions/{f['name']}",
            RAW / "sec" / f"submissions_{f['name']}",
        )
        pages.append(json.loads(t) if t else {})
    out = [
        (num, fd)
        for sub in pages
        for form, fd, num in zip(
            sub.get("form", []),
            sub.get("filingDate", []),
            sub.get("accessionNumber", []),
        )
        if form in ("10-K", "20-F") and fd < before
    ]
    return sorted(set(out), key=lambda r: r[1], reverse=True)


def xbrl_instance(cik: int, num: str) -> str:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{num.replace('-', '')}"
    idx = fetch(f"{base}/index.json", RAW / "sec" / "filings" / f"{num}_index.json")
    if not idx:
        return ""
    names = [f["name"] for f in json.loads(idx)["directory"]["item"]]
    inst = next((n for n in names if n.endswith("_htm.xml")), "") or next(
        (n for n in names if re.search(r"\d{8}\.xml$", n) and "_" not in n), ""
    )
    return (
        fetch(f"{base}/{inst}", RAW / "sec" / "filings" / f"{num}_{inst}")
        if inst
        else ""
    )


def product_revenue(cik: int, drug: str, before: str) -> dict:
    """Yearly product revenue for `drug` from the XBRL of the last annual report before `before`.
    Prefers a US-only figure; returns {} when the product is not tagged."""
    key = re.sub(r"[^a-z]", "", drug.split("/")[0].lower())
    for num, fd in annual_reports(cik, before)[:2]:
        x = xbrl_instance(cik, num) or ""
        if not x:
            continue
        ctx = {}
        for cid, body in re.findall(
            r'<(?:xbrli:)?context id="([^"]+)">(.*?)</(?:xbrli:)?context>', x, re.DOTALL
        ):
            members = re.findall(r'dimension="([^"]+)">([^<]+)<', body)
            dates = re.findall(r"<(?:xbrli:)?(startDate|endDate)>([^<]+)<", body)
            if len(dates) == 2 and any(
                key in m.lower().replace("_", "") for _, m in members
            ):
                start, end = dates[0][1], dates[1][1]
                if 330 <= _d(end) - _d(start) <= 380:
                    geo = [
                        m
                        for d, m in members
                        if "Geograph" in d or "Country" in m or "country:" in m
                    ]
                    other = [
                        m
                        for d, m in members
                        if "Product" not in d and "Geograph" not in d
                    ]
                    ctx[cid] = (end, geo, other)
        best = None
        other_ccy = ""
        plain = {}
        for cid, body in re.findall(
            r'<(?:xbrli:)?context id="([^"]+)">(.*?)</(?:xbrli:)?context>', x, re.DOTALL
        ):
            dates = re.findall(r"<(?:xbrli:)?(?:startDate|endDate)>([^<]+)<", body)
            if (
                "dimension=" not in body
                and len(dates) == 2
                and 330 <= _d(dates[1]) - _d(dates[0]) <= 380
            ):
                plain[cid] = dates[1]
        units = dict(
            re.findall(
                r'<(?:xbrli:)?unit id="([^"]+)">\s*<(?:xbrli:)?measure>([^<]+)<', x
            )
        )
        facts = []
        for m in re.finditer(
            r"<(?:us-gaap|ifrs-full):(Revenue\w*|SalesRevenue\w*)([^>]*)>([\d.]+)<", x
        ):
            cid = (
                re.search(r'contextRef="([^"]+)"', m.group(2)) or re.search("()", "")
            ).group(1)
            unit = (
                re.search(r'unitRef="([^"]+)"', m.group(2)) or re.search("()", "")
            ).group(1)
            if re.fullmatch(r"(?i)(iso4217[_:])?usd", units.get(unit, unit)):
                facts.append((m.group(1), cid, m.group(3)))
            elif cid in ctx:
                other_ccy = units.get(unit, unit).split(":")[-1]
        total = {}
        for tag, cid, val in facts:
            if cid in plain:
                total[plain[cid]] = max(total.get(plain[cid], 0), float(val))
        for tag, cid, val in facts:
            if cid not in ctx:
                continue
            end, geo, other = ctx[cid]
            us = any(
                re.search(r"(?i)(^|:)US$|UnitedStates|CountryUsMember$|:USMember$", g)
                for g in geo
            )
            if geo and not us:
                continue
            score = (end, us, not other)
            if best is None or score > best[0]:
                best = (score, float(val), end, us, num, fd)
        if best:
            return {
                "value": best[1],
                "fy_end": best[2],
                "us_only": best[3],
                "accession": best[4],
                "filed": best[5],
                "company_total": total.get(best[2]),
            }
        if other_ccy:
            return {"currency": other_ccy}
    return {}


# ------------------------------------------------------------------ Federal Circuit appeals
FLIP = {"win": "loss", "loss": "win", "split": "split"}
GOOD = {
    ("brand", "win"): "good",
    ("brand", "loss"): "bad",
    ("challenger", "win"): "bad",
}
GOOD |= {("challenger", "loss"): "good"}


def disposition(text: str, kind: str) -> str:
    if "RULE 36" in kind:
        return "AFFIRMED"
    flat = re.sub(r"\s+", " ", text)
    # The majority's disposition line sits just above "COSTS"; a dissent may follow it.
    words = r"\b((?:AFFIRMED|REVERSED|VACATED|DISMISSED)(?:[A-Z ,\-]|AND)*?)\s+"
    m = re.search(words + r"COSTS\b", flat) or re.search(words + r"Case: \d", flat)
    if m:
        return re.sub(r"[ ,\-]+", "-", m.group(1).strip(" ,-"))
    tail = flat[-4000:]
    for d in (
        "AFFIRMED-IN-PART",
        "AFFIRMED IN PART",
        "VACATED",
        "REVERSED",
        "AFFIRMED",
        "DISMISSED",
    ):
        if d in tail:
            return d.replace(" ", "-")
    return ""


def appeal_rows(rows: list[dict], bench: dict, ciks: dict) -> list[dict]:
    """One row per listed party for each Federal Circuit decision on appeal from a post-trial
    decision in the list. District dockets come from the opinion's caption ("Appeal from ...
    in No. 1:20-cv-00755"); appeals of preliminary-injunction rulings are left out."""
    origin = json.loads((OUT / "work" / "cafc_origin.json").read_text())
    by_docket = {}
    for r in rows:
        related = re.findall(r"Related dockets?: ([\d\-; ]+\d)", r.get("notes", ""))
        for d in r["docket_number"].split("; ") + "; ".join(related).split("; "):
            if d:
                by_docket.setdefault((r["court"], d.strip()), []).append(r)
    court = {"Delaware": "ded", "NewJersey": "njd", "WestVirginia": "wvnd"}
    out, seen = [], set()
    for key, o in sorted(origin.items()):
        appeal, date = key.split("@")
        day = f"{date[6:]}-{date[:2]}-{date[3:5]}"
        text = pdf_text(o["url"])
        head = re.sub(r"\s+", " ", text[:5000]).lower()
        if "preliminary injunction" in head and "bench trial" not in head:
            continue
        hits = []
        for d in o["dockets"]:
            yy, num = d.split("-cv-")
            hits += by_docket.get(
                (court.get((o["court"] or [""])[0], ""), f"{yy}-{int(num)}"), []
            )
        hits = [h for h in hits if h["decision_date"] and h["decision_date"] < day]
        latest = {}
        for h in hits:
            k = h.get("ticker", "") or h["case_id"]
            if k not in latest or h["decision_date"] > latest[k]["decision_date"]:
                latest[k] = h
        hits = list(latest.values())
        disp = disposition(text, o["kind"])
        for h in hits:
            if (h["case_id"], appeal, h.get("ticker", "")) in seen:
                continue
            seen.add((h["case_id"], appeal, h.get("ticker", "")))
            lower = h["outcome"]
            outcome = (
                lower
                if disp == "AFFIRMED"
                else FLIP.get(lower, "split")
                if disp == "REVERSED"
                else "split"
            )
            row = {c: h.get(c, "") for c in COLUMNS} | {
                "case_id": f"{h['case_id']}-cafc-{appeal}",
                "case_type": "drug_patent_appeal",
                "court": "cafc",
                "docket_number": appeal,
                "docket_url": "https://www.cafc.uscourts.gov/home/case-information/opinions-orders/",
                "decision_date": day,
                "decision_time_et": "",
                "decision_known_in_advance": "no",
                "decision_source_url": o["url"],
                "outcome": outcome,
                "outcome_for_company": GOOD.get(
                    (h.get("company_role", ""), outcome),
                    "mixed" if h.get("ticker", "") else "",
                ),
                "days_filed_to_decision": _d(day) - _d(h.get("filed_date", ""))
                if h.get("filed_date", "")
                else "",
                "confidence": h.get("confidence", "medium") if disp else "low",
                "sources": "Federal Circuit opinion PDF (cafc.uscourts.gov); district row "
                + h["case_id"],
                "first_public_source": "Federal Circuit opinions page",
                "first_public_time_et": day,
                "time_precision": "day",
                "during_market_hours": "unknown",
                "company_release_time_et": "",
                "lead_minutes_vs_company_release": "",
                "minutes_to_half_move": "",
                "settlement_amount_usd": "",
                "implied_move_before_decision": "",
            }
            n = [
                (
                    f"Appeal of the {h['decision_date']} district decision ({lower} for the brand); "
                    f"Federal Circuit disposition: {disp or 'not parsed'} ({o['status']})."
                )
            ]
            for c in (
                "ret_decision_day",
                "abn_ret_decision_day",
                "ret_decision_plus5",
                "adv_usd_20d_before_decision",
            ):
                row[c] = ""
            bars = yahoo(h.get("ticker", "")) if h.get("ticker", "") else {}
            ev = event_returns(bars, bench, day, two_day=True) if bars else {}
            if ev:
                row["ret_decision_day"], row["abn_ret_decision_day"] = (
                    ev["ret"],
                    ev["abn"],
                )
                row["ret_decision_plus5"], row["adv_usd_20d_before_decision"] = (
                    ev["plus5"],
                    ev["adv"],
                )
                n.append(
                    "Decision return is 2-day (posting time unknown), benchmark XBI."
                )
            cik = ciks.get(h.get("ticker", ""), (None, ""))[0]
            if cik:
                rel = company_release(cik, day)
                row["company_release_time_et"] = rel
            row["minute_data_available"] = (
                h.get("minute_data_available", "no") if h.get("ticker", "") else "no"
            )
            if h.get("ticker", ""):
                today = time.strftime("%Y-%m-%d")
                two = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 730 * 86400))
                row["minute_data_available"] = "yes" if two <= day <= today else "no"
            row["notes"] = " ".join(n)
            out.append(row)
    return out


if __name__ == "__main__":
    {
        "mods": stage_mods,
        "cafc": stage_cafc,
        "dedsite": stage_dedsite,
        "trials": stage_trials,
        "scan": stage_scan,
        "build": stage_build,
        "cltimes": stage_cltimes,
        "settlecheck": stage_settlecheck,
        "settle_edgar": stage_settle_edgar,
        "settledocket": stage_settledocket,
        "settlesearch": stage_settlesearch,
    }[sys.argv[1]](*[int(a) for a in sys.argv[2:]])
