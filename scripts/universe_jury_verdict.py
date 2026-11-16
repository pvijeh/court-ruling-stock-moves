"""Universe of large US jury verdicts involving US-listed companies, 2021 to today.

Stages (run in order; every download is cached under data/universe/jury_verdict/raw/):
  collect   discovery sources -> raw/*.csv
            * TopVerdict.com yearly top-100 and commercial top-100 lists (case names, amounts)
            * SEC EDGAR full-text search (efts) for verdict wording in 8-K, 10-Q, 10-K
            * Google News RSS headlines, one query set per month
  snippets  verdict sentences pulled out of every 8-K hit -> raw/efts_snippets.csv
  build     hand-checked case list (data/universe/jury_verdict/curated.csv) joined to
            Yahoo daily prices and SEC XBRL facts -> data/universe/jury_verdict/cases.csv

Helpers are copied from scripts/common.py on purpose so this file can change on its own.
Public, free sources only. CourtListener is not called here (125 requests/day cap).
"""

from __future__ import annotations

import csv
import email.utils
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "jury_verdict"
RAW = OUT / "raw"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
WEB_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
ET = ZoneInfo("America/New_York")
START = date(2021, 1, 1)
TODAY = date(2026, 10, 14)

_last: dict[str, float] = {}
_GAP = {
    "sec.gov": 0.15,
    "news.google.com": 1.5,
    "topverdict.com": 2.0,
    "yahoo.com": 2.0,
    "nasdaq.com": 1.0,
}


def _throttle(host: str) -> None:
    for key, gap in _GAP.items():
        if host.endswith(key):
            wait = _last.get(key, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[key] = time.time()


def get(url: str, tries: int = 2) -> str:
    """Cached GET ('' on failure). Cache key is a hash of the URL."""
    sub = RAW / "http"
    sub.mkdir(parents=True, exist_ok=True)
    host = urllib.parse.urlparse(url).hostname or ""
    key = (
        sub
        / f"{host.replace('.', '_')}_{hashlib.sha1(url.encode()).hexdigest()[:16]}.txt"
    )
    if key.exists():
        return key.read_text()
    ua = SEC_UA if host.endswith("sec.gov") else WEB_UA
    for i in range(tries):
        _throttle(host)
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=40)
        except requests.RequestException:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 200:
            key.write_text(r.text)
            return r.text
        if r.status_code in (202, 429, 500, 503):
            time.sleep(10 * (i + 1))
            continue
        return ""
    return ""


def strip_tags(t: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def write_csv(path: Path, rows: list[dict], cols: list[str] | None = None) -> None:
    cols = cols or (list(rows[0].keys()) if rows else [])
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- collect

TV_LISTS = ["top-100-verdicts", "top-100-commercial-litigation-verdicts"]
TV_PAGES = {"top-100": ["top-10", "top-20", "top-50", "top-100"]}


def topverdict() -> list[dict]:
    rows = []
    for year in range(START.year, TODAY.year + 1):
        for lst in TV_LISTS:
            for size in TV_PAGES["top-100"]:
                url = f"https://topverdict.com/lists/{year}/united-states/{lst.replace('top-100', size)}"
                t = strip_tags(get(url))
                for m in re.finditer(
                    r"(\d{1,3}) Amount: \$([\d,\.]+) Attorneys: .*? Case: (.*?) Type: (.*?) State: ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
                    t,
                ):
                    rows.append(
                        {
                            "year": year,
                            "list": lst,
                            "rank": int(m.group(1)),
                            "amount_usd": float(m.group(2).replace(",", "")),
                            "case": m.group(3).strip(),
                            "type": m.group(4).strip()[:200],
                            "state": m.group(5).strip()[:40],
                            "url": url,
                        }
                    )
    seen, out = set(), []
    for r in rows:
        k = (r["year"], r["list"], r["rank"], r["case"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    write_csv(RAW / "topverdict_entries.csv", out)
    return out


EFTS_QUERIES = [
    '"jury verdict"',
    '"jury returned a verdict"',
    '"jury awarded"',
    '"the jury found"',
    '"jury found that"',
    '"returned a verdict"',
    '"jury trial" verdict damages',
]
EFTS_FORMS = ["8-K", "10-Q", "10-K", "6-K", "20-F"]


def efts_hits() -> list[dict]:
    rows: dict = {}
    # year windows keep each query under efts's 10,000-hit cap
    for q in EFTS_QUERIES:
        for form in EFTS_FORMS:
            for year in range(START.year, TODAY.year + 1):
                s = f"{year}-01-01"
                e = f"{year}-12-31" if year < TODAY.year else TODAY.isoformat()
                page = 0
                while True:
                    params = {
                        "q": q,
                        "forms": form,
                        "dateRange": "custom",
                        "startdt": s,
                        "enddt": e,
                    }
                    if page:
                        params["from"] = str(page * 100)
                    txt = get(
                        "https://efts.sec.gov/LATEST/search-index?"
                        + urllib.parse.urlencode(params)
                    )
                    if not txt:
                        break
                    d = json.loads(txt)
                    hits = d.get("hits", {}).get("hits", [])
                    for h in hits:
                        src = h["_source"]
                        adsh, doc = h["_id"].split(":", 1)
                        k = (adsh, doc)
                        r = rows.setdefault(
                            k,
                            {
                                "adsh": adsh,
                                "doc": doc,
                                "cik": (src.get("ciks") or [""])[0],
                                "name": (src.get("display_names") or [""])[0],
                                "form": src.get("form", ""),
                                "file_type": src.get("file_type", ""),
                                "file_date": src.get("file_date", ""),
                                "items": " ".join(src.get("items") or []),
                                "sics": " ".join(src.get("sics") or []),
                                "queries": "",
                            },
                        )
                        if q not in r["queries"]:
                            r["queries"] = (r["queries"] + " | " + q).strip(" |")
                    total = d.get("hits", {}).get("total", {}).get("value", 0)
                    page += 1
                    if page * 100 >= min(total, 10000) or not hits:
                        break
    out = sorted(rows.values(), key=lambda r: (r["file_date"], r["adsh"]))
    write_csv(RAW / "efts_hits.csv", out)
    return out


NEWS_QUERIES = [
    "jury verdict million",
    "jury verdict billion",
    'jury "ordered to pay" million',
    "jury awards million company",
    "patent jury verdict million",
    "jury verdict patent infringement",
    "jury verdict talc OR Roundup OR earplug OR bellwether",
    'jury verdict "trade secrets" million',
    "jury verdict antitrust million",
    'jury verdict "breach of contract" million',
    "jury verdict shares fall OR stock drops",
    "jury verdict shares rise OR stock jumps",
    '"jury" "verdict" "Inc." million',
]


def news() -> list[dict]:
    rows = {}
    m0 = date(START.year, START.month, 1)
    while m0 <= TODAY:
        m1 = date(m0.year + (m0.month == 12), m0.month % 12 + 1, 1)
        for q in NEWS_QUERIES:
            full = f"{q} after:{m0.isoformat()} before:{m1.isoformat()}"
            url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
                {"q": full, "hl": "en-US", "gl": "US", "ceid": "US:en"}
            )
            t = get(url)
            for it in re.findall(r"<item>(.*?)</item>", t, re.DOTALL):
                title = html.unescape(
                    (re.findall(r"<title>(.*?)</title>", it, re.DOTALL) or [""])[0]
                )
                link = re.search(r"<link>(.*?)</link>", it)
                pub = re.search(r"<pubDate>(.*?)</pubDate>", it)
                if not pub:
                    continue
                dt = email.utils.parsedate_to_datetime(pub.group(1)).astimezone(UTC)
                k = title.lower()
                if k not in rows:
                    rows[k] = {
                        "pub_utc": dt.isoformat(),
                        "title": title,
                        "link": link.group(1) if link else "",
                        "query": q,
                    }
        m0 = m1
    out = sorted(rows.values(), key=lambda r: r["pub_utc"])
    write_csv(RAW / "news_headlines.csv", out)
    return out


# ---------------------------------------------------------------- snippets

VERDICT_SENT = re.compile(r"(?i)\b(jury|verdict)\b")
MONEY = re.compile(r"(?i)\$\s?[\d,.]+\s*(million|billion)?")


def snippets(forms: tuple[str, ...] = ("8-K", "6-K")) -> None:
    hits = [
        h
        for h in read_csv(RAW / "efts_hits.csv")
        if h["form"].split("/")[0] in forms
        and (
            h["file_type"].split("/")[0] in forms or h["file_type"].startswith("EX-99")
        )
    ]
    out = []
    for h in hits:
        cik = int(h["cik"])
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{h['adsh'].replace('-', '')}/{h['doc']}"
        t = strip_tags(get(url))
        sents = re.split(r"(?<=[.;])\s+(?=[A-Z(])", t)
        keep = [
            s
            for s in sents
            if VERDICT_SENT.search(s) and (MONEY.search(s) or "verdict" in s.lower())
        ]
        out.append({**h, "url": url, "snippet": " || ".join(s[:400] for s in keep[:6])})
    write_csv(RAW / "efts_snippets.csv", out)


# ---------------------------------------------------------------- build

# Hand-checked case list. Each row was matched to its verdict by reading the cited sources.
CURATED = """\
case_id,case_name,court,ticker,company,company_role,counterparty,counterparty_ticker,decision_date,verdict_usd,outcome,outcome_for_company,confidence,sources,notes
jv-2021-vlsi-intel,VLSI Technology LLC v. Intel Corp.,W.D. Tex. (Waco),INTC,Intel Corp.,defendant,VLSI Technology LLC (Fortress),,2021-03-02,2175000000,loss,bad,medium,Bloomberg 2021-03-02; TopVerdict 2021 #2,Federal Circuit vacated the $2.18B damages and ordered a new damages trial 2023-12-04; PTAB also found some claims unpatentable (Jun 2023)
jv-2022-vlsi-intel,VLSI Technology LLC v. Intel Corp. (second trial),W.D. Tex. (Austin),INTC,Intel Corp.,defendant,VLSI Technology LLC (Fortress),,2022-11-15,948800000,loss,bad,medium,Reuters 2022-11-16; TopVerdict 2022 #6,
jv-2021-pmc-apple,Personalized Media Communications v. Apple Inc.,E.D. Tex.,AAPL,Apple Inc.,defendant,Personalized Media Communications,,2021-08-05,308500000,loss,bad,medium,Reuters 2021-08-06; TopVerdict 2021 #6,
jv-2021-optis-apple,Optis Wireless v. Apple Inc. (damages retrial),E.D. Tex.,AAPL,Apple Inc.,defendant,Optis Wireless Technology,,2021-08-11,300000000,loss,bad,medium,Reuters 2021-08-13,
jv-2021-most-team,Most v. Team Industrial Services Inc.,Texas state court (Brazoria County),TISI,Team Inc.,defendant,Estate of Most,,2021-06-01,222000000,loss,bad,medium,Wichita Eagle 2021-06-02; Team 8-K 2021-06-22; TopVerdict 2021 #8,
jv-2021-malibu,Estate of R.P.B. v. Malibu Boats,Georgia state court (Rabun County),MBUU,Malibu Boats Inc.,defendant,Batchelder family,,2021-08-27,200000000,loss,bad,medium,AJC 2021-08-30; Malibu 10-K 2021-08-31,
jv-2021-plexxikon-novartis,Plexxikon Inc. v. Novartis Pharmaceuticals Corp.,N.D. Cal.,NVS,Novartis AG,defendant,Plexxikon (Daiichi Sankyo),,2021-07-22,177800000,loss,bad,medium,Reuters 2021-07-23; Fierce Pharma 2021-07-23; TopVerdict 2021 #11,
jv-2021-wapp-microfocus,Wapp Tech Corp. v. Micro Focus International plc,E.D. Tex.,MFGP,Micro Focus International plc,defendant,Wapp Tech,,2021-03-05,172500000,loss,bad,high,Micro Focus 6-K/annual report: verdict 5 March 2021,MFGP ADR delisted after OpenText takeover Jan 2023
jv-2021-diaz-tesla,Diaz v. Tesla Inc.,N.D. Cal.,TSLA,Tesla Inc.,defendant,Owen Diaz,,2021-10-04,136900000,loss,bad,medium,CNBC 2021-10-04; TopVerdict 2021 #16,remitted to $15M Apr 2022; retrial Apr 2023 $3.2M
jv-2021-zest-walmart,Zest Labs v. Walmart Inc.,W.D. Ark.,WMT,Walmart Inc.,defendant,Zest Labs (Ecoark),ZEST,2021-04-09,115000000,loss,bad,high,Ecoark 8-K 2021-04-12; Arkansas Democrat-Gazette 2021-04-11,judge granted new trial (2022); retrial verdict 2025-05-13 $222M
jv-2021-zest-walmart-p,Zest Labs v. Walmart Inc.,W.D. Ark.,ZEST,Ecoark Holdings Inc.,plaintiff,Walmart Inc.,WMT,2021-04-09,115000000,win,good,high,Ecoark 8-K 2021-04-12,judge granted new trial (2022); retrial verdict 2025-05-13 $222M
jv-2025-zest-walmart,Zest Labs v. Walmart Inc. (retrial),W.D. Ark.,WMT,Walmart Inc.,defendant,Zest Labs,,2025-05-13,222000000,loss,bad,medium,Reuters 2025-05-14; TopVerdict 2025,
jv-2021-ingevity-basf,Ingevity Corp. v. BASF Corp. (antitrust counterclaim),D. Del.,NGVT,Ingevity Corp.,defendant,BASF Corp.,,2021-09-14,84900000,loss,bad,high,Ingevity 8-K 2021-09-16 ($28.3M trebled),
jv-2021-opioid-ohio-cvs,Lake and Trumbull Counties v. CVS et al. (opioid),N.D. Ohio,CVS,CVS Health Corp.,defendant,Lake and Trumbull Counties,,2021-11-23,650600000,loss,bad,medium,Reuters 2021-11-23; NYT 2021-11-23,liability-only jury verdict; judge set $650.6M abatement Aug 2022; Ohio Supreme Court threw out the public-nuisance theory and the $650.6M award on 2024-12-10
jv-2021-opioid-ohio-wba,Lake and Trumbull Counties v. CVS et al. (opioid),N.D. Ohio,WBA,Walgreens Boots Alliance,defendant,Lake and Trumbull Counties,,2021-11-23,650600000,loss,bad,medium,Reuters 2021-11-23,liability-only jury verdict; abatement set by judge Aug 2022; Ohio Supreme Court threw out the award on 2024-12-10
jv-2021-opioid-ohio-wmt,Lake and Trumbull Counties v. CVS et al. (opioid),N.D. Ohio,WMT,Walmart Inc.,defendant,Lake and Trumbull Counties,,2021-11-23,650600000,loss,bad,medium,Reuters 2021-11-23,liability-only jury verdict; abatement set by judge Aug 2022; Ohio Supreme Court threw out the award on 2024-12-10
jv-2022-appian-pega,Appian Corp. v. Pegasystems Inc.,Virginia state court (Fairfax County),PEGA,Pegasystems Inc.,defendant,Appian Corp.,APPN,2022-05-09,2036000000,loss,bad,high,Appian 8-K 2022-05-10 (verdict May 9 2022 after seven-week trial); Pega 8-K 2022-05-10,Virginia Court of Appeals reversed and ordered a new trial 2024-07-30; Virginia Supreme Court agreed to hear Appian appeal Mar 2025
jv-2022-appian-pega-p,Appian Corp. v. Pegasystems Inc.,Virginia state court (Fairfax County),APPN,Appian Corp.,plaintiff,Pegasystems Inc.,PEGA,2022-05-09,2036000000,win,good,high,Appian 8-K 2022-05-10,Virginia Court of Appeals reversed and ordered a new trial 2024-07-30; Virginia Supreme Court agreed to hear Appian appeal Mar 2025
jv-2022-hill-ford,Hill v. Ford Motor Co.,Georgia state court (Gwinnett County),F,Ford Motor Co.,defendant,Hill family,,2022-08-19,1724000000,settled,bad,medium,Reuters/AP 2022-08-21,verdict Friday Aug 19 2022; Ford settled the Georgia cases Sep 2025 (AJC 2025-09-15)
jv-2022-bmo-petters,Kelley v. BMO Harris Bank,D. Minn.,BMO,Bank of Montreal,defendant,Petters bankruptcy trustee,,2022-11-08,563700000,loss,bad,high,BMO 6-K 2022-11-09; BMO 6-K 2022-12-01 (provision $1.12B),
jv-2022-sce-martinez,Martinez v. Southern California Edison,Los Angeles Superior Court,EIX,Edison International,defendant,two former employees,,2022-06-01,464500000,loss,bad,medium,LA Times 2022-06-02,
jv-2022-harris-fedex,Harris v. FedEx Corporate Services,S.D. Tex.,FDX,FedEx Corp.,defendant,Jennifer Harris,,2022-10-28,366000000,loss,bad,medium,FedEx 10-Q 2022-11-01; Reuters 2022-11-01,punitive cut to ~$249k by judge 2023
jv-2022-kamuda-sotera,Kamuda v. Sterigenics U.S.,Cook County Circuit Court,SHC,Sotera Health Co.,defendant,Susan Kamuda,,2022-09-19,363000000,loss,bad,medium,Chicago Tribune 2022-09-19,settled Willowbrook cases for $408M Jan 2023
jv-2022-cgi-illumina,Complete Genomics v. Illumina,D. Del.,ILMN,Illumina Inc.,defendant,Complete Genomics (BGI),,2022-05-06,333800000,loss,bad,medium,Endpoints 2022-05-09; TopVerdict 2022 #12,
jv-2022-monster-vpx,Monster Energy v. Vital Pharmaceuticals (Bang),C.D. Cal.,MNST,Monster Beverage Corp.,plaintiff,Vital Pharmaceuticals,,2022-09-29,293000000,win,good,medium,Reuters 2022-09-30,VPX bankrupt Oct 2022
jv-2022-ravgen-labcorp,Ravgen Inc. v. Laboratory Corp. of America,W.D. Tex.,LH,Labcorp,defendant,Ravgen,,2022-09-23,272500000,loss,bad,medium,Reuters 2022-09-26,
jv-2022-usaa-pnc,USAA v. PNC Bank,E.D. Tex.,PNC,PNC Financial Services,defendant,USAA,,2022-05-13,218450000,loss,bad,medium,Reuters 2022-05-16,
jv-2022-columbia-norton,Columbia University v. NortonLifeLock,E.D. Va.,GEN,NortonLifeLock (Gen Digital),defendant,Columbia University,,2022-04-29,185100000,loss,bad,medium,Columbia press release 2022-05-02,judge raised award to $481M for willful infringement (2022); Federal Circuit reversed on patent eligibility Mar 2026 (IPWatchdog 2026-03-11)
jv-2022-teva-lilly,Teva v. Eli Lilly (Emgality patents),D. Mass.,LLY,Eli Lilly & Co.,defendant,Teva,TEVA,2022-11-09,176500000,loss,bad,medium,Reuters 2022-11-09,judge set aside verdict (JMOL) Sep 2023
jv-2022-teva-lilly-p,Teva v. Eli Lilly (Emgality patents),D. Mass.,TEVA,Teva Pharmaceutical,plaintiff,Eli Lilly & Co.,LLY,2022-11-09,176500000,win,good,medium,Reuters 2022-11-09,judge set aside verdict (JMOL) Sep 2023
jv-2022-sony-fleur,Fleur v. Sony Music Holdings,Georgia state court (DeKalb County),SONY,Sony Group Corp.,defendant,families of two shooting victims,,2022-12-16,160000000,loss,bad,low,WSB-TV 2022-12-18,Sony Music subsidiary as event promoter
jv-2022-ncl-abb,NCL Ltd. v. ABB Oy (Azipod),Florida state court (Miami-Dade),NCLH,Norwegian Cruise Line Holdings,plaintiff,ABB Oy,ABB,2022-10-28,158750000,win,good,medium,Maritime Executive 2022-10-31,ABB ADR delisted from NYSE 2023
jv-2022-3m-earplug,In re 3M Combat Arms Earplug (Sloan/Wayman bellwether),N.D. Fla.,MMM,3M Co.,defendant,two Army veterans,,2022-01-27,110000000,loss,bad,medium,NYT 2022-01-28,largest earplug bellwether; 3M settled MDL $6B Aug 2023
jv-2022-pcb-allison,Allison et al. v. Monsanto (Sky Valley PCB),King County Superior Court,BAYRY,Bayer AG (OTC ADR),defendant,Sky Valley school plaintiffs,,2022-10-13,275000000,loss,bad,medium,Reuters 2022-10-14,Bayer trades OTC in US (not exchange-listed)
jv-2021-pcb-erickson,Erickson v. Pharmacia (Sky Valley PCB),King County Superior Court,BAYRY,Bayer AG (OTC ADR),defendant,three teachers,,2021-07-28,185000000,loss,bad,medium,Guardian 2021-07-29,Pharmacia is Pfizer unit; Monsanto/Bayer indemnifies
jv-2023-pcb-heit,Heit v. Pharmacia (Sky Valley PCB),King County Superior Court,BAYRY,Bayer AG (OTC ADR),defendant,school employees,,2023-11-17,165000000,loss,bad,low,Law360 2023-11-20,
jv-2023-pcb-bard,Bard v. Pharmacia (Sky Valley PCB),King County Superior Court,BAYRY,Bayer AG (OTC ADR),defendant,former students and parents,,2023-12-18,857000000,loss,bad,medium,Reuters 2023-12-18,
jv-2023-roundup-caranci,Caranci v. Monsanto (Roundup),Philadelphia Court of Common Pleas,BAYRY,Bayer AG (OTC ADR),defendant,Ernest Caranci,,2023-10-27,175000000,loss,bad,medium,CNBC 2023-10-27,
jv-2023-roundup-draeger,Draeger et al. v. Monsanto (Roundup),Missouri state court (Cole County),BAYRY,Bayer AG (OTC ADR),defendant,three plaintiffs,,2023-11-17,1560000000,loss,bad,medium,Reuters 2023-11-20,verdict Friday Nov 17 2023; reduced to $611M Feb 2024
jv-2024-roundup-mckivison,McKivison v. Monsanto (Roundup),Philadelphia Court of Common Pleas,BAYRY,Bayer AG (OTC ADR),defendant,John McKivison,,2024-01-26,2250000000,loss,bad,medium,Bloomberg 2024-01-26,cut to ~$400M by judge
jv-2025-roundup-barnes,Barnes v. Monsanto (Roundup),Georgia state court (Cobb County),BAYRY,Bayer AG (OTC ADR),defendant,John Barnes,,2025-03-21,2100000000,loss,bad,medium,Washington Post 2025-03-22; Reuters 2025-03-24,
jv-2023-nar-burnett,Burnett v. National Association of Realtors,W.D. Mo.,BRK-B,Berkshire Hathaway (HomeServices),defendant,home sellers class,,2023-10-31,1785000000,loss,bad,medium,Reuters 2023-10-31,HomeServices settled $250M Apr 2024; trebled exposure ~$5.4B
jv-2023-netlist-samsung,Netlist v. Samsung,E.D. Tex.,NLST,Netlist Inc. (OTC),plaintiff,Samsung Electronics,,2023-04-21,303000000,win,good,high,Netlist 8-K 2023-04-25; Reuters 2023-04-21,Netlist trades OTCQB
jv-2023-dxc-tata,Computer Sciences Corp. v. Tata Consultancy Services,N.D. Tex.,DXC,DXC Technology,plaintiff,Tata Consultancy Services,,2023-11-20,210000000,win,good,medium,Reuters 2023-11-21,
jv-2023-cpi-vivint,CPI Security Systems v. Vivint Smart Home,W.D.N.C.,NRG,NRG Energy (Vivint parent),defendant,CPI Security,,2023-02-16,190000000,loss,bad,medium,Charlotte Observer 2023-02-17,NRG agreed to buy Vivint Dec 2022 (closed Mar 10 2023); VVNT still listed on verdict day
jv-2023-cpi-vivint-v,CPI Security Systems v. Vivint Smart Home,W.D.N.C.,VVNT,Vivint Smart Home,defendant,CPI Security,,2023-02-16,190000000,loss,bad,medium,Charlotte Observer 2023-02-17,pending NRG cash takeover capped price moves
jv-2023-finesse-att,Finesse Wireless v. AT&T Mobility and Nokia,E.D. Tex.,T,AT&T Inc.,defendant,Finesse Wireless,,2023-01-13,166000000,loss,bad,medium,Reuters 2023-01-17,Federal Circuit overturned the verdict 2025-09-24; Supreme Court denied review Jun 2026
jv-2023-finesse-nokia,Finesse Wireless v. AT&T Mobility and Nokia,E.D. Tex.,NOK,Nokia Oyj,defendant,Finesse Wireless,,2023-01-13,166000000,loss,bad,low,Reuters 2023-01-17,joint award with AT&T; Federal Circuit overturned the verdict 2025-09-24
jv-2023-unp-johnson,Johnson v. Union Pacific Railroad,Texas state court (Harris County),UNP,Union Pacific Corp.,defendant,Bianca Johnson,,2023-03-03,557000000,loss,bad,medium,Bloomberg Law 2023-03-06; Railway Age,
jv-2023-fhfa-fannie,Fairholme / Berkley v. FHFA (net worth sweep),D.D.C.,FNMA,Fannie Mae (OTC),defendant,preferred and common shareholders,,2023-08-14,612400000,loss,mixed,medium,American Banker 2023-08-15; Fannie 10-Q 2023-10-31,shareholders of FNMA themselves won; common stock rose
jv-2023-fhfa-freddie,Fairholme / Berkley v. FHFA (net worth sweep),D.D.C.,FMCC,Freddie Mac (OTC),defendant,preferred and common shareholders,,2023-08-14,612400000,loss,mixed,low,American Banker 2023-08-15,
jv-2024-gas-verizon,General Access Solutions v. Verizon,E.D. Tex.,VZ,Verizon Communications,defendant,General Access Solutions,,2024-06-27,847000000,settled,bad,medium,Bloomberg Law 2024-06-28,judge granted Verizon a new trial 2024-10-01 (Reuters); settled Dec 2024
jv-2024-gill-exxon,Gill v. Exxon Mobil (benzene),Philadelphia Court of Common Pleas,XOM,Exxon Mobil Corp.,defendant,Paul Gill,,2024-05-09,725500000,loss,bad,medium,Reuters 2024-05-10,trial judge upheld the verdict (Law.com 2025-05-16)
jv-2024-kove-amazon,Kove IO v. Amazon Web Services,N.D. Ill.,AMZN,Amazon.com Inc.,defendant,Kove IO,,2024-04-10,525000000,loss,bad,medium,Reuters 2024-04-10,
jv-2024-gill-abbott,Gill v. Abbott Laboratories (NEC formula),St. Louis City Circuit Court,ABT,Abbott Laboratories,defendant,Kaitlyn Gill,,2024-07-26,495000000,loss,bad,high,Reuters 2024-07-26; Abbott 10-Q 2026 (Mo. Ct. App. affirmed May 2026),
jv-2024-wabash-perkins,Perkins v. Wabash National,St. Louis City Circuit Court,WNC,Wabash National Corp.,defendant,families of two crash victims,,2024-09-06,462000000,loss,bad,high,Wabash 8-K 2024-09-06; FreightWaves 2024-09-06,judge reduced punitive; adjusted award ~$122M (Wabash 8-K Mar 2025)
jv-2024-insulet-eoflow,Insulet Corp. v. EOFlow,D. Mass.,PODD,Insulet Corp.,plaintiff,EOFlow Co.,,2024-12-03,452000000,win,good,high,Insulet 8-K 2024-12-04 (verdict Dec 3 2024),
jv-2024-netlist-micron,Netlist v. Micron Technology,E.D. Tex.,MU,Micron Technology,defendant,Netlist Inc.,NLST,2024-05-23,445000000,loss,bad,medium,Reuters 2024-05-23,
jv-2024-netlist-micron-p,Netlist v. Micron Technology,E.D. Tex.,NLST,Netlist Inc. (OTC),plaintiff,Micron Technology,MU,2024-05-23,445000000,win,good,medium,Reuters 2024-05-23,Netlist trades OTCQB
jv-2024-uhs-pavilion,Patient v. Pavilion Behavioral Health System,Illinois state court (Champaign County),UHS,Universal Health Services,defendant,former patient,,2024-03-29,535000000,loss,bad,high,UHS 8-K 2024-04-01,
jv-2024-uhs-cumberland,A.B.E. v. Cumberland Hospital,W.D. Va.,UHS,Universal Health Services,defendant,former patient,,2024-09-26,360000000,loss,bad,high,UHS 8-K 2024-09-30; WTVR 2024-09-27,
jv-2024-mrtech-wdc,MR Technologies v. Western Digital,C.D. Cal.,WDC,Western Digital Corp.,defendant,MR Technologies GmbH,,2024-07-29,262000000,loss,bad,high,Reuters 2024-07-30; WDC 10-K 2024-07-31,
jv-2024-spex-wdc,SPEX Technologies v. Western Digital,C.D. Cal.,WDC,Western Digital Corp.,defendant,SPEX Technologies,,2024-10-18,315700000,loss,bad,high,WDC 10-Q 2024-10-24 (verdict Oct 18 2024); Reuters 2024-10-18,
jv-2024-hog-morris,Morris v. Harley-Davidson,New York state court (Livingston County),HOG,Harley-Davidson Inc.,defendant,Morris family,,2024-08-13,287000000,loss,bad,medium,RochesterFirst 2024-08-13; HOG 10-Q 2025-05-01,
jv-2024-netlist-samsung2,Netlist v. Samsung (second trial),E.D. Tex.,NLST,Netlist Inc. (OTC),plaintiff,Samsung Electronics,,2024-11-22,118000000,win,good,medium,Reuters 2024-11-22,
jv-2024-sarepta-ns,Nippon Shinyaku v. Sarepta Therapeutics,D. Del.,SRPT,Sarepta Therapeutics,plaintiff,Nippon Shinyaku,,2024-12-20,115200000,win,good,medium,ETPharma 2024-12-21,Sarepta won on its counterclaim
jv-2024-cmc-psg,Pacific Steel Group v. Commercial Metals Co.,N.D. Cal.,CMC,Commercial Metals Co.,defendant,Pacific Steel Group,,2024-11-08,110000000,loss,bad,low,Fastmarkets 2024-11-12,antitrust (trebling possible); CMC appealing as of Oct 2025
jv-2024-tagrisso-azn,Puma Biotechnology and Wyeth v. AstraZeneca (Tagrisso),D. Del.,AZN,AstraZeneca plc,defendant,Pfizer (Wyeth) and Puma Biotechnology,PFE,2024-05-16,107500000,loss,bad,high,Puma 8-K 2024-05-17; Reuters 2024-05-17,
jv-2024-tagrisso-pfe,Puma Biotechnology and Wyeth v. AstraZeneca (Tagrisso),D. Del.,PFE,Pfizer Inc.,plaintiff,AstraZeneca,AZN,2024-05-16,107500000,win,good,high,Puma 8-K 2024-05-17,
jv-2024-tagrisso-pbyi,Puma Biotechnology and Wyeth v. AstraZeneca (Tagrisso),D. Del.,PBYI,Puma Biotechnology,plaintiff,AstraZeneca,AZN,2024-05-16,107500000,win,good,high,Puma 8-K 2024-05-17,Puma shares in damages with Pfizer
jv-2024-hetsler-ford,Hetsler v. Ford Motor Co.,Florida state court (Duval County),F,Ford Motor Co.,defendant,Hetsler family,,2024-02-22,104600000,loss,bad,low,Florida Times-Union 2024-02-23,
jv-2024-ll-walmart,London Luxury v. Walmart Inc.,W.D. Ark.,WMT,Walmart Inc.,defendant,London Luxury LLC,,2024-04-05,101000000,loss,bad,low,Arkansas Times 2024-04-09,
jv-2024-icp-cat,International Construction Products v. Caterpillar,D. Del.,CAT,Caterpillar Inc.,defendant,International Construction Products,,2024-04-16,100000000,loss,bad,medium,Reuters 2024-04-17,antitrust; trebling possible
jv-2024-natera-caredx,Natera v. CareDx,D. Del.,CDNA,CareDx Inc.,defendant,Natera Inc.,NTRA,2024-01-26,96300000,loss,bad,medium,Reuters 2024-01-29,qualifies by size vs CareDx market cap
jv-2024-paltalk-cisco,Paltalk Holdings v. Cisco Systems,W.D. Tex.,PALT,Paltalk Inc.,plaintiff,Cisco Systems,CSCO,2024-08-29,65700000,win,good,high,Paltalk 8-K 2024-08-30 and 2024-10-11,
jv-2024-jnj-lee,Lee v. Johnson & Johnson (talc),Oregon state court (Multnomah County),JNJ,Johnson & Johnson,defendant,Kyung Lee,,2024-06-03,260000000,loss,bad,medium,Reuters 2024-06-04,
jv-2024-silica-caesarstone,Gomez (silicosis) v. Caesarstone et al.,Los Angeles Superior Court,CSTE,Caesarstone Ltd.,defendant,Gustavo Reyes Gonzalez,,2024-08-06,52400000,loss,bad,medium,Caesarstone 6-K 2024-08-08; LA Times 2024-08-07,share of award vs Caesarstone partial
jv-2024-qorvo-akoustis,Qorvo v. Akoustis Technologies,D. Del.,AKTS,Akoustis Technologies,defendant,Qorvo Inc.,QRVO,2024-05-17,38800000,loss,bad,high,Akoustis 8-K 2024-05-20,Akoustis filed Chapter 11 Dec 2024
jv-2024-skillz-avia,Skillz Platform v. AviaGames,N.D. Cal.,SKLZ,Skillz Inc.,plaintiff,AviaGames,,2024-02-09,42900000,win,good,medium,Reuters 2024-02-10,settled Apr 2024
jv-2024-finch-ferring,Ferring v. Finch Therapeutics,D. Del.,FNCH,Finch Therapeutics,plaintiff,Ferring Pharmaceuticals,,2024-08-09,25000000,win,good,medium,Reuters 2024-08-09; Finch 8-K 2024-08-12,
jv-2024-markforged,Continuous Composites v. Markforged,D. Del.,MKFG,Markforged Holding,defendant,Continuous Composites,,2024-04-12,17000000,loss,bad,medium,3D Printing Industry 2024-04-15,settled Sep 2024
jv-2024-meec-coal,Midwest Energy Emissions v. Vistra et al.,D. Del.,MEEC,Midwest Energy Emissions (OTC),plaintiff,refined-coal defendants,,2024-03-01,57000000,win,good,medium,Reuters 2024-03-04; MEEC 8-K 2024-03-05,
jv-2024-rpm-trade-secret,trade-secret case v. RPM International (Oregon),Oregon state court (Jackson County),RPM,RPM International,defendant,White City business,,2024-09-27,190000000,loss,bad,medium,RPM 8-K 2024-09-30; Rogue Valley Times 2024-09-30,
jv-2025-mills-ford,Estate of Mills v. Ford Motor Co.,Georgia state court (Muscogee County),F,Ford Motor Co.,defendant,Mills family,,2025-02-14,2500000000,settled,bad,medium,Ledger-Enquirer 2025-02-14,"Ford moved for new trial Mar 2025; Ford settled the Georgia cases Sep 2025 (AJC 2025-09-15), amount undisclosed"
jv-2025-et-greenpeace,Energy Transfer v. Greenpeace,North Dakota state court (Morton County),ET,Energy Transfer LP,plaintiff,Greenpeace,,2025-03-19,667000000,win,good,medium,Reuters 2025-03-19,Greenpeace post-trial motions to cut the award filed May 2025; judge-reduced amount not confirmed
jv-2025-masimo-apple,Masimo v. Apple,C.D. Cal.,AAPL,Apple Inc.,defendant,Masimo Corp.,MASI,2025-11-14,634000000,loss,bad,medium,Reuters 2025-11-14,judge denied Apple post-trial motions and new trial Jul 2026
jv-2025-masimo-apple-p,Masimo v. Apple,C.D. Cal.,MASI,Masimo Corp.,plaintiff,Apple Inc.,AAPL,2025-11-14,634000000,win,good,medium,Reuters 2025-11-14,judge denied Apple post-trial motions and new trial Jul 2026
jv-2025-google-privacy,Rodriguez v. Google (Web & App Activity),N.D. Cal.,GOOGL,Alphabet Inc.,defendant,user class,,2025-09-03,425700000,loss,bad,medium,Reuters 2025-09-03,
jv-2025-google-cell,Csupo v. Google (cellular data),Santa Clara County Superior Court,GOOGL,Alphabet Inc.,defendant,Android user class,,2025-07-01,314600000,loss,bad,medium,Reuters 2025-07-01,
jv-2025-tesla-benavides,Benavides v. Tesla (Autopilot),S.D. Fla.,TSLA,Tesla Inc.,defendant,Benavides family,,2025-08-01,243000000,loss,bad,medium,Reuters 2025-08-01,
jv-2025-headwater-verizon,Headwater Research v. Verizon,E.D. Tex.,VZ,Verizon Communications,defendant,Headwater Research,,2025-07-23,175000000,settled,bad,medium,Reuters 2025-07-24; Reuters 2025-08-21 (settled),settled Aug 2025
jv-2025-expressmobile-gddy,Express Mobile v. GoDaddy,D. Del.,GDDY,GoDaddy Inc.,defendant,Express Mobile,,2025-11-06,170000000,loss,bad,medium,Reuters 2025-11-07,
jv-2025-whatsapp-nso,WhatsApp v. NSO Group,N.D. Cal.,META,Meta Platforms,plaintiff,NSO Group,,2025-05-06,167700000,win,good,medium,Reuters 2025-05-06,
jv-2025-omnicare-cvs,U.S. ex rel. Bassan v. Omnicare (CVS),S.D.N.Y.,CVS,CVS Health Corp.,defendant,United States,,2025-04-29,136000000,loss,bad,medium,McKnight's 2025-04-30; Reuters 2025-07-08,judge set $949M in trebled damages and penalties Jul 2025
jv-2025-tot-apple,TOT Power Control v. Apple,D. Del.,AAPL,Apple Inc.,defendant,TOT Power Control,,2025-06-30,110700000,loss,bad,low,Reuters 2025-07-01,
jv-2025-chevron-plaquemines,Plaquemines Parish v. Chevron (coastal),Louisiana state court (Plaquemines Parish),CVX,Chevron Corp.,defendant,Plaquemines Parish,,2025-04-04,744600000,loss,bad,medium,AP 2025-04-04; NOLA.com,"US Supreme Court held 2026-04-17 the case belongs in federal court, undermining the verdict"
jv-2025-seminole-wfc,Seminole Tribe v. Wells Fargo Bank,Florida state court (Broward County),WFC,Wells Fargo & Co.,defendant,Seminole Tribe minors trust,,2025-03-24,826000000,loss,bad,medium,Sun Sentinel 2025-03-25,
jv-2025-jnj-craft,Craft v. Johnson & Johnson (talc),Baltimore City Circuit Court,JNJ,Johnson & Johnson,defendant,talc plaintiff,,2025-12-19,1560000000,loss,bad,medium,Reuters 2025-12-22; Bloomberg 2025-12-22,
jv-2025-jnj-moore,Estate of Moore v. Johnson & Johnson (talc),Los Angeles Superior Court,JNJ,Johnson & Johnson,defendant,Mae Moore family,,2025-10-06,966000000,loss,bad,medium,Reuters 2025-10-07,
jv-2026-ardagh-sam,Ardagh Metal Packaging v. Boston Beer,N.D. Ill.,SAM,Boston Beer Co.,defendant,Ardagh Metal Packaging,AMBP,2026-04-09,175500000,loss,bad,high,Boston Beer 8-K 2026-04-10; Law360 2026-04-10,
jv-2026-ardagh-sam-p,Ardagh Metal Packaging v. Boston Beer,N.D. Ill.,AMBP,Ardagh Metal Packaging,plaintiff,Boston Beer Co.,SAM,2026-04-09,175500000,win,good,high,Ardagh 6-K 2026-04-23,
jv-2026-nektar-lilly,Nektar Therapeutics v. Eli Lilly,US district court (venue not confirmed),NKTR,Nektar Therapeutics,plaintiff,Eli Lilly,LLY,2026-09-24,90000000,win,good,medium,Reuters 2026-09-25; Nektar 8-K 2026-09-25,breach of implied covenant on the rezpeg collaboration; TradingView 2026-09-22 reports jury deliberating; first reports Sep 25 morning
jv-2026-beckman-cytek,Beckman Coulter v. Cytek Biosciences,D. Del.,CTKB,Cytek Biosciences,defendant,Beckman Coulter (Danaher),DHR,2026-08-20,56000000,loss,bad,high,Reuters 2026-08-21; Cytek 10-Q 2026-08-24,
jv-2026-shintech-olin,Shintech v. Olin,Texas state court (venue not confirmed),OLN,Olin Corp.,defendant,Shintech,,2026-02-11,75000000,loss,bad,low,Olin press release (PR Newswire) 2026-02-12; Business Journals 2026-02-12,verdict day not confirmed (press release Feb 12 says recent verdict); Olin took $75M charge
jv-2026-impulse-innovex,Impulse v. Innovex International,Texas?,INVX,Innovex International,defendant,Impulse,,2026-03-09,47600000,loss,bad,low,Innovex 8-K 2026-03-11,
jv-2026-acadia-fv,addiction counselor v. Fashion Valley (Acadia),San Diego Superior Court,ACHC,Acadia Healthcare,defendant,former counselor,,2026-05-15,105000000,loss,bad,medium,San Diego Union-Tribune 2026-05-16; Acadia 8-K 2026-05-18,
jv-2026-skillz-papaya,Skillz Platform v. Papaya Gaming (false advertising),New York (court not confirmed),SKLZ,Skillz Inc.,plaintiff,Papaya Gaming,,2026-04-22,420000000,win,good,medium,Bloomberg Law 2026-04-23; GamesBeat 2026-04-23; Quiver Quantitative 2026-04-23,trial began Apr 14 2026; Skillz shares spiked on the verdict; later reports of $719M with enhanced damages unconfirmed
jv-2026-apple-haptics,Taction Technology v. Apple Inc. (haptics patents),US district court (venue not confirmed),AAPL,Apple Inc.,defendant,Taction Technology (funded by Burford Capital),,2026-09-25,5700000000,loss,bad,medium,Bloomberg Law 2026-09-25; Engadget 2026-09-26; NDTV Profit 2026-09-26,"largest US patent verdict on record per reports; Burford Capital (BUR) funds the plaintiff but is not a party, so no BUR row; verdict day could be Sep 24 or 25"
jv-2026-ramaco-chubb,Ramaco Resources v. Chubb (insurance),S.D. W.Va.,METC,Ramaco Resources,plaintiff,Chubb,CB,2026-09-28,30000000,win,good,medium,Ramaco press release (PR Newswire) 2026-09-28; PropertyCasualty360 2026-09-30,decision_date is the first public report (Mon Sep 28); the verdict may have come late the prior week
jv-2026-ameris,former executive v. Ameris Bank,US court (venue not confirmed),ABCB,Ameris Bancorp,defendant,former executive,,2026-06-11,79950000,loss,bad,medium,TradingView 2026-06-12; American Banker 2026-06-16; Banking Dive 2026-06-17,wrongful termination; Ameris says it will appeal
jv-2022-fontaine-pm,Fontaine v. Philip Morris USA,Massachusetts Superior Court (Suffolk County),MO,Altria Group,defendant,Fontaine estate,,2022-09-19,1008000000,loss,bad,medium,CVN 2022-09-20; TopVerdict 2022 #4,Philip Morris USA is an Altria subsidiary
jv-2022-siqueiros-gm,Siqueiros v. General Motors (engine class action),N.D. Cal.,GM,General Motors,defendant,owner class,,2022-10-04,102600000,loss,bad,medium,Reuters 2022-10-05; TopVerdict 2022 #37,
jv-2022-voxer-meta,Voxer v. Meta Platforms,W.D. Tex.,META,Meta Platforms,defendant,Voxer Inc.,,2022-09-21,174500000,loss,bad,medium,Bloomberg Law 2022-09-21; TechCrunch 2022-09-22,
jv-2023-touchstream-google,Touchstream Technologies v. Google,W.D. Tex.,GOOGL,Alphabet Inc.,defendant,Touchstream,,2023-07-21,338700000,loss,bad,medium,Reuters 2023-07-24; Ars Technica 2023-07-24,verdict date inferred from Monday reporting
jv-2023-textron-dji,Textron Innovations v. SZ DJI Technology,W.D. Tex.,TXT,Textron Inc.,plaintiff,DJI,,2023-04-21,279000000,win,good,medium,Bloomberg Law 2023-04-21; Reuters 2023-04-24,
jv-2023-roundup-dennis,Dennis v. Monsanto (Roundup),San Diego Superior Court,BAYRY,Bayer AG (OTC ADR),defendant,Mike Dennis,,2023-10-31,332000000,loss,bad,medium,Reuters 2023-10-31,
jv-2023-colibri-mdt,Colibri Heart Valve v. Medtronic CoreValve,C.D. Cal.,MDT,Medtronic plc,defendant,Colibri Heart Valve,,2023-02-10,106500000,loss,bad,medium,MedTech Dive 2023-02-13,verdict day inferred from Monday reporting; Federal Circuit reversed 2025-07-18
jv-2023-acadia-desert-hills,foster-care plaintiff v. Desert Hills (Acadia),New Mexico state court (Bernalillo County),ACHC,Acadia Healthcare,defendant,former foster child,,2023-07-10,485000000,settled,bad,medium,AP 2023-07-11; Acadia 8-K 2023-07-11; BHB 2023-10-31 ($400M settlement),Acadia settled related claims for $400M Oct 2023
jv-2024-propel-psx,Propel Fuels v. Phillips 66,California state court (Alameda County),PSX,Phillips 66,defendant,Propel Fuels,,2024-10-16,604900000,loss,bad,medium,Business Wire 2024-10-17; Reuters 2024-10-17; TopVerdict 2024,verdict day inferred as the trading day before the first dated report (2024-10-17); the 2-day return covers both days; trade secrets; judge later added exemplary damages (unconfirmed)
jv-2024-ipa-msft,IPA Technologies v. Microsoft (Cortana),D. Del.,MSFT,Microsoft Corp.,defendant,IPA Technologies,,2024-05-09,242000000,settled,bad,medium,Bloomberg Law 2024-05-10; Reuters 2024-05-10; Reuters 2024-06-20 (settled),verdict day inferred as the trading day before the first dated report (2024-05-10); the 2-day return covers both days; settled Jun 2024
jv-2024-gratton-ups,Gratton v. United Parcel Service,E.D. Wash.,UPS,United Parcel Service,defendant,Tyrone Gratton,,2024-09-12,238000000,loss,bad,medium,Bloomberg Law 2024-09-13; Seattle Times 2024-09-14,verdict day inferred as the trading day before the first dated report (2024-09-13); the 2-day return covers both days; judge cut the award by nearly $200M Nov 2024
jv-2024-guardant-natera-p,Guardant Health v. Natera (false advertising),N.D. Cal.,GH,Guardant Health,plaintiff,Natera Inc.,NTRA,2024-11-25,292500000,win,good,medium,Fierce Biotech 2024-11-26; TopVerdict 2024,verdict day inferred as the trading day before the first dated report (2024-11-26); the 2-day return covers both days
jv-2024-guardant-natera,Guardant Health v. Natera (false advertising),N.D. Cal.,NTRA,Natera Inc.,defendant,Guardant Health,GH,2024-11-25,292500000,loss,bad,medium,Fierce Biotech 2024-11-26; TopVerdict 2024,verdict day inferred as the trading day before the first dated report (2024-11-26); the 2-day return covers both days
jv-2024-centripetal-panw,Centripetal Networks v. Palo Alto Networks,E.D. Va.,PANW,Palo Alto Networks,defendant,Centripetal Networks,,2024-01-31,151500000,loss,bad,medium,WSJ 2024-02-01; Business Journals 2024-02-02,verdict day inferred as the trading day before the first dated report (2024-02-01); the 2-day return covers both days
jv-2025-regeneron-amgen-p,"Regeneron v. Amgen (antitrust, Praluent)",D. Del.,REGN,Regeneron Pharmaceuticals,plaintiff,Amgen Inc.,AMGN,2025-05-14,406800000,win,good,medium,Fierce Pharma 2025-05-15; Orrick 2025-05-16,verdict day inferred as the trading day before the first dated report (2025-05-15); the 2-day return covers both days
jv-2025-regeneron-amgen,"Regeneron v. Amgen (antitrust, Praluent)",D. Del.,AMGN,Amgen Inc.,defendant,Regeneron Pharmaceuticals,REGN,2025-05-14,406800000,loss,bad,medium,Fierce Pharma 2025-05-15; Orrick 2025-05-16,verdict day inferred as the trading day before the first dated report (2025-05-15); the 2-day return covers both days
jv-2025-innovative-biosense,Innovative Health v. Biosense Webster (J&J),C.D. Cal.,JNJ,Johnson & Johnson,defendant,Innovative Health,,2025-05-15,147000000,loss,bad,medium,Law360 2025-05-16; MedTech Dive 2025-05-20,verdict day inferred as the trading day before the first dated report (2025-05-16); the 2-day return covers both days; judge trebled to $442M Jun 2025
jv-2025-norguard-brk,Salguero-Quijada v. Norguard Insurance (Berkshire),Colorado state court (Denver),BRK-B,Berkshire Hathaway,defendant,Salguero-Quijada,,2025-04-10,145000000,loss,bad,medium,CVN 2025-04-11; Denver Post 2025-04-11,verdict day inferred as the trading day before the first dated report (2025-04-11); the 2-day return covers both days
jv-2025-jwaluminum-cb,JW Aluminum v. ACE American Insurance (Chubb),South Carolina (court not confirmed),CB,Chubb Ltd.,defendant,JW Aluminum,,2025-11-20,112000000,loss,bad,low,Law.com 2025-11-21; Post and Courier 2025-11-25,verdict day inferred as the trading day before the first dated report (2025-11-21); the 2-day return covers both days; other insurers also defendants; Chubb share not confirmed
jv-2022-caredx-natera,CareDx v. Natera (false advertising),D. Del.,CDNA,CareDx Inc.,plaintiff,Natera Inc.,NTRA,2022-03-14,44900000,win,good,medium,Reuters 2022-03-15; TopVerdict 2022,verdict day inferred as the trading day before the first dated report (2022-03-15); the 2-day return covers both days; about 2% of CareDx market cap
jv-2023-twinstrand-guardant,TwinStrand Biosciences v. Guardant Health,D. Del.,GH,Guardant Health,defendant,TwinStrand Biosciences,,2023-11-14,83400000,loss,bad,medium,Reuters 2023-11-15; Fierce Biotech 2023-11-15,verdict day inferred as the trading day before the first dated report (2023-11-15); the 2-day return covers both days
jv-2023-avnet-nippon,Avnet v. Nippon Chemi-Con et al. (capacitor price-fixing),N.D. Cal.,AVT,Avnet Inc.,plaintiff,Nippon Chemi-Con and others,,2023-05-22,268000000,win,good,medium,Reuters 2023-05-23; PYMNTS 2023-05-23,verdict day inferred as the trading day before the first dated report (2023-05-23); the 2-day return covers both days; $268M is after trebling ($89M jury award)
"""


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
BIOTECH_SIC = {"2834", "2835", "2836", "8731"}
# ordinary shares per US-traded ADR, for 20-F filers whose dei share count is in ordinary shares
ADR_RATIO = {
    "AZN": 0.5,
    "HMC": 3.0,
    "NVS": 1.0,
    "SONY": 1.0,
    "SHEL": 2.0,
    "EQNR": 1.0,
    "ABB": 1.0,
    "BMO": 1.0,
}
REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenuesNetOfInterestExpense",
]
POLYGON_START = date(2024, 10, 15)  # free plan: about 2 years of 1-minute bars


ETFS = {"SPY", "XBI"}
_yahoo_blocked = False


def nasdaq_daily(sym: str) -> list:
    """Split-adjusted (not dividend-adjusted) closes from Nasdaq's public quote API, 2021 on."""
    cls = "etf" if sym in ETFS else "stocks"
    nsym = sym.replace("-", ".")
    txt = get(
        f"https://api.nasdaq.com/api/quote/{nsym}/historical?assetclass={cls}"
        f"&fromdate=2021-01-01&todate={TODAY.isoformat()}&limit=9999"
    )
    try:
        rows = json.loads(txt)["data"]["tradesTable"]["rows"]
    except (ValueError, KeyError, TypeError):
        return []
    out = []
    for r in reversed(rows):
        try:
            c = float(r["close"].replace("$", "").replace(",", ""))
            v = float(r["volume"].replace(",", "") or 0)
        except (ValueError, AttributeError):
            continue
        out.append((datetime.strptime(r["date"], "%m/%d/%Y").date(), c, c * v, c))
    return out


def daily(sym: str) -> list:
    """Yahoo first (dividend-adjusted, 2015 on); Nasdaq if Yahoo is rate-limiting this box."""
    global _yahoo_blocked
    if not _yahoo_blocked:
        out = yahoo_daily(sym)
        if out:
            return out
        _yahoo_blocked = _yahoo_probe_failed()
    return nasdaq_daily(sym) or polygon_daily(sym)


def polygon_daily(sym: str) -> list:
    """Polygon daily bars; the free plan only reaches about 2 years back."""
    import os

    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        return []
    cache = RAW / "polygon" / f"{sym}_daily.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        bars = json.loads(cache.read_text())
    else:
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/{POLYGON_START}/{TODAY}"
            f"?adjusted=true&sort=asc&limit=50000&apiKey={key}"
        )
        time.sleep(13)
        try:
            bars = requests.get(url, timeout=40).json().get("results") or []
        except (requests.RequestException, ValueError):
            return []
        cache.write_text(json.dumps(bars))
    return [
        (
            datetime.fromtimestamp(b["t"] / 1000, tz=UTC).astimezone(ET).date(),
            b["c"],
            b["c"] * b["v"],
            b["c"],
        )
        for b in bars
    ]


def _yahoo_probe_failed() -> bool:
    try:
        r = requests.get(
            "https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=5d&interval=1d",
            headers={"User-Agent": WEB_UA},
            timeout=20,
        )
    except requests.RequestException:
        return True
    return r.status_code == 429


def yahoo_daily(sym: str) -> list:
    """(date, adjusted close, dollar volume) per trading day, 2015 to today."""
    p1 = int(datetime(2015, 1, 1, tzinfo=UTC).timestamp())
    p2 = int(datetime(TODAY.year, TODAY.month, TODAY.day, tzinfo=UTC).timestamp())
    txt = get(
        f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit"
    )
    try:
        res = json.loads(txt)["chart"]["result"][0]
    except (ValueError, KeyError, TypeError, IndexError):
        return []
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
    out = []
    for t, a, c, v in zip(ts, adj, q["close"], q["volume"]):
        if a is None or c is None:
            continue
        d = datetime.fromtimestamp(t, tz=UTC).astimezone(ET).date()
        out.append((d, a, c * (v or 0), c))
    return out


def sec_json(url: str) -> dict:
    t = get(url)
    try:
        return json.loads(t) if t else {}
    except ValueError:
        return {}


def cik_map() -> dict[str, str]:
    d = json.loads((RAW / "company_tickers.json").read_text())
    return {v["ticker"].upper(): str(v["cik_str"]) for v in d.values()}


def shares_at(facts: dict, d: date) -> float | None:
    rows = (
        facts.get("facts", {})
        .get("dei", {})
        .get("EntityCommonStockSharesOutstanding", {})
        .get("units", {})
        .get("shares", [])
    )
    rows = [r for r in rows if r.get("filed", "9999") <= d.isoformat()]
    if not rows:
        return None
    last = max(r["end"] for r in rows)
    if (d - date.fromisoformat(last)).days > 400:
        return None
    by_end = {}
    for r in rows:
        if r["end"] == last:
            by_end[r.get("accn", "") + r.get("frame", "") + str(r["val"])] = r["val"]
    # several share classes are reported as separate facts with the same end date
    accns: dict = {}
    for r in rows:
        if r["end"] == last:
            accns.setdefault(r["accn"], []).append(r["val"])
    vals = max(accns.values(), key=len)
    return float(sum(vals))


def revenue_ttm(facts: dict, d: date) -> float | None:
    usg = facts.get("facts", {}).get("us-gaap", {})
    best = None
    for tag in REVENUE_TAGS:
        rows = usg.get(tag, {}).get("units", {}).get("USD", [])
        rows = [
            r
            for r in rows
            if r.get("filed", "9999") <= d.isoformat() and r.get("start")
        ]
        if not rows:
            continue
        q, fy = {}, {}
        for r in rows:
            n = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
            if 80 <= n <= 100:
                q[(r["start"], r["end"])] = r["val"]
            elif 350 <= n <= 380:
                fy[(r["start"], r["end"])] = r["val"]
        for (s0, e0), v in fy.items():
            inside = [(k, x) for k, x in q.items() if k[0] >= s0 and k[1] <= e0]
            if len(inside) == 3:
                last_end = max(k[1] for k, _ in inside)
                q.setdefault((last_end, e0), v - sum(x for _, x in inside))
        ends = sorted(q, key=lambda k: k[1], reverse=True)[:4]
        cand = None
        if (
            len(ends) == 4
            and (date.fromisoformat(ends[0][1]) - date.fromisoformat(ends[3][0])).days
            < 380
        ):
            cand = (ends[0][1], sum(q[k] for k in ends))
        elif fy:
            k = max(fy, key=lambda k: k[1])
            cand = (k[1], fy[k])
        if (
            cand
            and (d - date.fromisoformat(cand[0])).days < 500
            and (best is None or cand[0] > best[0])
        ):
            best = cand
    if best is None:
        ifrs = (
            facts.get("facts", {})
            .get("ifrs-full", {})
            .get("Revenue", {})
            .get("units", {})
            .get("USD", [])
        )
        ifrs = [
            r
            for r in ifrs
            if r.get("filed", "9999") <= d.isoformat() and r.get("start")
        ]
        ifrs = [
            r
            for r in ifrs
            if 350
            <= (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
            <= 380
        ]
        if ifrs:
            r = max(ifrs, key=lambda r: r["end"])
            best = (r["end"], r["val"])
    return float(best[1]) if best else None


def idx_on_or_after(days: list, d: date) -> int | None:
    for i, row in enumerate(days):
        if row[0] >= d:
            return i
    return None


def ret(days: list, i: int | None, n: int = 1) -> float | None:
    if i is None or i - 1 < 0 or i + n - 1 >= len(days):
        return None
    return days[i + n - 1][1] / days[i - 1][1] - 1


def polygon_minutes(sym: str, d: date) -> list[dict]:
    import os

    key = os.environ.get("POLYGON_API_KEY")
    if not key or d < POLYGON_START:
        return []
    cache = RAW / "polygon" / f"{sym}_{d.isoformat()}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return json.loads(cache.read_text())
    url = f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/{d}/{d}?adjusted=true&sort=asc&limit=50000&apiKey={key}"
    for _ in range(3):
        time.sleep(13)  # free plan: 5 requests a minute
        try:
            r = requests.get(url, timeout=40)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            bars = r.json().get("results") or []
            cache.write_text(json.dumps(bars))
            return bars
        if r.status_code != 429:
            return []
    return []


def minutes_to_half(sym: str, t: datetime) -> tuple[str, str]:
    bars = polygon_minutes(sym, t.date())
    if not bars:
        return "", "no"
    rows = [
        (datetime.fromtimestamp(b["t"] / 1000, tz=UTC).astimezone(ET), b["c"])
        for b in bars
    ]
    reg = [r for r in rows if r[0].time() < datetime.strptime("16:00", "%H:%M").time()]
    before = [c for tm, c in reg if tm < t]
    after = [(tm, c) for tm, c in reg if tm >= t]
    if not before or not after:
        return "", "yes"
    p0, close = before[-1], after[-1][1]
    half = p0 + (close - p0) / 2
    for tm, c in after:
        if (close >= p0 and c >= half) or (close < p0 and c <= half):
            return str(int((tm - t).total_seconds() // 60)), "yes"
    return "", "yes"


def parse_et(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=ET)
        except ValueError:
            pass
    return None


def fnum(x) -> str:
    if x is None or x == "":
        return ""
    if isinstance(x, float):
        return f"{x:.6g}" if abs(x) < 10 else f"{x:.0f}"
    return str(x)


def earnings_in_window(sub: dict, days: list, i: int, n: int) -> str:
    """Acceptance time (ET) of an earnings 8-K that hit the price inside days[i : i + n], if any."""
    rec = (sub.get("filings") or {}).get("recent") or {}
    if i < 1 or i + n - 1 >= len(days):
        return ""
    start = datetime.combine(days[i - 1][0], datetime.min.time(), ET).replace(hour=16)
    end = datetime.combine(days[i + n - 1][0], datetime.min.time(), ET).replace(hour=16)
    for form, items, acc in zip(
        rec.get("form", []), rec.get("items", []), rec.get("acceptanceDateTime", [])
    ):
        if form == "8-K" and "2.02" in items:
            t = datetime.fromisoformat(acc).astimezone(ET)
            if start <= t < end:
                return t.strftime("%Y-%m-%d %H:%M")
    return ""


def verdict_8k(cik: str, sub: dict, d: date) -> tuple[str, str]:
    """Earliest 8-K/6-K by this company that EDGAR full-text search matched on verdict wording,
    filed 0-4 days after the verdict. Returns (acceptance time ET, filing URL)."""
    hits = RAW / "efts_hits.csv"
    if not cik or not hits.exists():
        return "", ""
    rec = (sub.get("filings") or {}).get("recent") or {}
    acc = dict(zip(rec.get("accessionNumber", []), rec.get("acceptanceDateTime", [])))
    best = None
    for h in read_csv(hits):
        if int(h["cik"]) != int(cik) or h["form"] not in ("8-K", "6-K"):
            continue
        fd = date.fromisoformat(h["file_date"])
        if not 0 <= (fd - d).days <= 4 or h["adsh"] not in acc:
            continue
        t = datetime.fromisoformat(acc[h["adsh"]]).astimezone(ET)
        if best is None or t < best[0]:
            best = (t, h["adsh"])
    if best is None:
        return "", ""
    a = best[1]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a.replace('-', '')}/{a}-index.htm"
    return best[0].strftime("%Y-%m-%d %H:%M"), url


def build() -> None:
    cur = list(csv.DictReader(io.StringIO(CURATED)))
    ciks = cik_map()
    bench_cache: dict[str, list] = {}
    out = []
    for c in cur:
        row = {k: c.get(k, "") for k in COLUMNS}
        row["case_type"] = "jury_verdict"
        row["decision_known_in_advance"] = "yes"
        notes = [c.get("notes", "")] if c.get("notes") else []
        tk = c["ticker"].strip()
        ysym = c.get("yahoo_symbol") or tk.replace(".", "-")
        cik = (
            c.get("cik")
            or ciks.get(tk.upper().replace("-", "."), "")
            or ciks.get(tk.upper(), "")
        )
        facts, sic, sub = {}, "", {}
        if cik:
            facts = sec_json(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
            )
            sub = sec_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
            sic = str(sub.get("sic", ""))
        bench = c.get("benchmark") or ("XBI" if sic in BIOTECH_SIC else "SPY")
        days = daily(ysym)
        if bench not in bench_cache:
            bench_cache[bench] = daily(bench)
        bdays = bench_cache[bench]
        if not days:
            notes.append(
                f"no free daily prices for {ysym} (Yahoo rate-limited; not on Nasdaq quote API or Polygon free 2-year window)"
            )
        filed = parse_et(c.get("filed_date", ""))
        dec = parse_et(c.get("decision_date", ""))
        dec_t = (
            parse_et(
                f"{c.get('decision_date', '')} {c.get('decision_time_et', '')}".strip()
            )
            if c.get("decision_time_et")
            else None
        )
        if filed and dec:
            row["days_filed_to_decision"] = (dec.date() - filed.date()).days

        # market cap and revenue at filing (XBRL), verdict share of market cap on the day before the verdict
        def mcap(d: date, facts=facts, days=days, tk=tk) -> float | None:
            sh = shares_at(facts, d) if facts else None
            i = idx_on_or_after(days, d)
            if sh is None or i is None or not days:
                return None
            j = i if days[i][0] == d else max(i - 1, 0)
            px = days[j][3]
            return sh * px / ADR_RATIO.get(tk, 1.0)

        if filed:
            row["market_cap_usd_at_filing"] = fnum(mcap(filed.date()))
            row["revenue_ttm_usd_at_filing"] = fnum(
                revenue_ttm(facts, filed.date()) if facts else None
            )
            i = idx_on_or_after(days, filed.date())
            bi = idx_on_or_after(bdays, filed.date())
            r, br = ret(days, i), ret(bdays, bi)
            if days and i is not None and days[i][0] == filed.date():
                row["ret_filing_day"] = fnum(r)
                row["abn_ret_filing_day"] = fnum(
                    r - br if r is not None and br is not None else None
                )
        verdict = float(c["verdict_usd"]) if c.get("verdict_usd") else None
        row["revenue_at_stake_usd"] = fnum(verdict)
        if dec:
            cap_before = mcap(dec.date() - timedelta(days=1))
            if verdict and cap_before:
                row["revenue_at_stake_share"] = fnum(verdict / cap_before)
                if not filed:
                    notes.append(
                        f"filing date not collected; market cap the day before the verdict was ${cap_before / 1e9:.2f}B"
                    )
            ddate, n = dec.date(), 1
            if dec_t is None:
                n = 2
                notes.append(
                    "verdict time unknown: decision-day return is the 2-day return (verdict day plus next)"
                )
            elif dec_t.hour >= 16:
                ddate = ddate + timedelta(days=1)
            i = idx_on_or_after(days, ddate)
            bi = idx_on_or_after(bdays, ddate)
            if days and i is not None:
                if days[i][0] != ddate and dec_t is not None and n == 1:
                    notes.append(
                        f"verdict on a non-trading day; decision day is {days[i][0]}"
                    )
                r, br = ret(days, i, n), ret(bdays, bi, n)
                row["ret_decision_day"] = fnum(r)
                row["abn_ret_decision_day"] = fnum(
                    r - br if r is not None and br is not None else None
                )
                row["ret_decision_plus5"] = fnum(ret(days, i, 5))
                er = earnings_in_window(sub, days, i, n)
                if er:
                    notes.append(
                        f"CAUTION: earnings release (8-K item 2.02) accepted {er} falls inside the decision-day window, so the move is not the verdict alone"
                    )
                if i >= 20:
                    row["adv_usd_20d_before_decision"] = fnum(
                        sum(x[2] for x in days[i - 20 : i]) / 20
                    )
        # speed columns
        if not c.get("first_public_time_et") and dec:
            row["first_public_source"] = (
                "jury verdict read in open court; first reports: "
                + c.get("sources", "").split(";")[0]
            )
            row["first_public_time_et"] = dec.date().isoformat()
            row["time_precision"] = "day"
        if not c.get("company_release_time_et") and dec:
            rt, rurl = verdict_8k(cik, sub, dec.date())
            if rt:
                row["company_release_time_et"] = rt
                notes.append(f"company release time = EDGAR acceptance of {rurl}")
        fp = parse_et(row.get("first_public_time_et", ""))
        prec = row.get("time_precision", "")
        if fp and prec in ("minute", "hour"):
            t = fp.time()
            open_ = (
                fp.weekday() < 5
                and datetime.strptime("09:30", "%H:%M").time()
                <= t
                < datetime.strptime("16:00", "%H:%M").time()
            )
            row["during_market_hours"] = "yes" if open_ else "no"
        else:
            row["during_market_hours"] = "unknown"
        cr = parse_et(row.get("company_release_time_et", ""))
        if fp and cr and prec == "minute" and len(row["company_release_time_et"]) > 10:
            row["lead_minutes_vs_company_release"] = int(
                (cr - fp).total_seconds() // 60
            )
        row["minute_data_available"] = "no"
        if (
            fp
            and prec == "minute"
            and row["during_market_hours"] == "yes"
            and fp.date() >= POLYGON_START
        ):
            m, avail = minutes_to_half(tk, fp)
            row["minutes_to_half_move"], row["minute_data_available"] = m, avail
        elif fp and fp.date() >= POLYGON_START and tk:
            row["minute_data_available"] = (
                "yes" if polygon_minutes(tk, fp.date()) else "no"
            )
        row["notes"] = "; ".join(n for n in notes if n)
        out.append(row)
    write_csv(OUT / "cases.csv", out, COLUMNS)
    print(f"{len(out)} rows -> {OUT / 'cases.csv'}")


# Unscheduled post-trial rulings that cut, erased or confirmed a verdict in the list above.
# (ticker, first dated report, what happened, source). The ruling time of day was not found in free sources.
POST_TRIAL = [
    (
        "INTC",
        "2023-12-04",
        "Federal Circuit vacates the $2.18B VLSI damages award",
        "Reuters 2023-12-04",
    ),
    (
        "PEGA",
        "2024-07-30",
        "Virginia Court of Appeals reverses the $2.04B Appian verdict",
        "Holland & Knight 2024-08-05",
    ),
    (
        "APPN",
        "2024-07-30",
        "Virginia Court of Appeals reverses the $2.04B Appian verdict",
        "Holland & Knight 2024-08-05",
    ),
    (
        "PEGA",
        "2025-03-07",
        "Virginia Supreme Court agrees to hear Appian's appeal",
        "PR Newswire 2025-03-07",
    ),
    (
        "CVS",
        "2024-12-10",
        "Ohio Supreme Court throws out the $650.6M opioid award",
        "Reuters 2024-12-10",
    ),
    (
        "WMT",
        "2024-12-10",
        "Ohio Supreme Court throws out the $650.6M opioid award",
        "Reuters 2024-12-10",
    ),
    (
        "VZ",
        "2024-10-01",
        "judge orders a new trial on the $847M patent verdict",
        "Reuters 2024-10-01",
    ),
    (
        "UPS",
        "2024-11-18",
        "judge cuts the $238M Gratton verdict by nearly $200M",
        "New York Post 2024-11-18",
    ),
    (
        "JNJ",
        "2025-06-06",
        "judge triples the Biosense Webster antitrust award to $442M",
        "Cardiovascular Business 2025-06-06",
    ),
    (
        "MDT",
        "2025-07-18",
        "Federal Circuit overturns the $106.5M Colibri verdict",
        "Reuters 2025-07-18",
    ),
    (
        "T",
        "2025-09-24",
        "Federal Circuit overturns the $166M Finesse verdict",
        "Reuters 2025-09-24",
    ),
    (
        "NOK",
        "2025-09-24",
        "Federal Circuit overturns the $166M Finesse verdict",
        "Reuters 2025-09-24",
    ),
    (
        "GEN",
        "2026-03-11",
        "Federal Circuit reverses the Columbia patent judgment",
        "IPWatchdog 2026-03-11",
    ),
    (
        "CVX",
        "2026-04-17",
        "US Supreme Court sends the Plaquemines case to federal court",
        "NOLA.com 2026-04-17",
    ),
    (
        "AAPL",
        "2026-07-21",
        "judge denies Apple's bid to overturn the $634M Masimo verdict",
        "9to5Mac 2026-07-21",
    ),
]


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def report() -> None:
    import statistics

    rows = read_csv(OUT / "cases.csv")
    cases = {(r["case_name"], r["decision_date"]) for r in rows}
    years: dict[str, set] = {}
    for r in rows:
        years.setdefault(r["decision_date"][:4], set()).add(
            (r["case_name"], r["decision_date"])
        )
    moved = [
        (abs(float(r["abn_ret_decision_day"])), r)
        for r in rows
        if r["abn_ret_decision_day"]
    ]
    moved.sort(key=lambda x: -x[0])
    absm = [m for m, _ in moved]
    over = {k: sum(m > k for m in absm) for k in (0.05, 0.10, 0.25)}
    ofc = {
        k: sum(r["outcome_for_company"] == k for r in rows)
        for k in ("good", "bad", "mixed", "unknown")
    }
    outc: dict[str, int] = {}
    for r in rows:
        outc[r["outcome"]] = outc.get(r["outcome"], 0) + 1
    tickers = {r["ticker"] for r in rows}
    small = [
        r
        for r in rows
        if r["revenue_at_stake_share"] and float(r["revenue_at_stake_share"]) >= 0.02
    ]
    under100 = [
        r
        for r in rows
        if r["revenue_at_stake_usd"] and float(r["revenue_at_stake_usd"]) < 1e8
    ]
    noprice = [r for r in rows if not r["abn_ret_decision_day"]]
    open_fast = [
        r
        for r in rows
        if r["during_market_hours"] == "yes" and r["decision_known_in_advance"] == "no"
    ]
    leads = [
        int(r["lead_minutes_vs_company_release"])
        for r in rows
        if r["lead_minutes_vs_company_release"]
    ]
    halves = [int(r["minutes_to_half_move"]) for r in rows if r["minutes_to_half_move"]]
    rel = [r for r in rows if r["company_release_time_et"]]
    rel_open = [
        r for r in rel if "09:30" <= r["company_release_time_et"][11:16] < "16:00"
    ]
    minute_ok = sum(r["minute_data_available"] == "yes" for r in rows)
    med = statistics.median(absm) if absm else 0
    conf10 = [r for m, r in moved if m > 0.10 and "CAUTION" in r["notes"]]
    confound = "".join(
        f" {r['company']}'s {abs(float(r['abn_ret_decision_day'])) * 100:.0f}% move came on the same two days as its quarterly results."
        for r in conf10
    )

    # stock moves around the post-trial rulings (2-day abnormal return: day before the report and report day)
    pt_lines = []
    bench = daily("SPY")
    for tk, d, what, src in POST_TRIAL:
        days = daily(tk)
        dd = date.fromisoformat(d)
        i, bi = idx_on_or_after(days, dd), idx_on_or_after(bench, dd)
        rr = bb = None
        if i is not None and bi is not None and i >= 1 and bi >= 1:
            rr, bb = ret(days, i - 1, 2), ret(bench, bi - 1, 2)
        mv = pct(rr - bb) if rr is not None and bb is not None else "no price data"
        pt_lines.append(
            (
                abs(rr - bb) if rr is not None and bb is not None else -1,
                f"- **{tk}, {d}:** {what}. Abnormal move {mv}. Source: {src}.",
            )
        )
    pt_lines.sort(key=lambda x: -x[0])

    L: list[str] = []
    w = L.append
    w(
        "# Large jury verdicts against or won by US-listed companies, 2021 to October 2026\n"
    )
    w("## Summary\n")
    w(
        f"- **What this is:** a list of every large US jury verdict we could find from 1 January 2021 to {TODAY.day} {TODAY:%B %Y} where a company with US-traded stock was the plaintiff (the side suing) or the defendant (the side being sued). A jury verdict is the jury's decision at the end of a trial, including how much money one side owes the other."
    )
    w(
        "- **Why it matters:** the aim is to estimate, before a case is decided, how much a company's stock is likely to move when it is. An earlier study picked 40 dramatic rulings by hand. That sample overstates the typical move, because quiet outcomes were left out. This list keeps the quiet ones."
    )
    w(
        "- **What counts:** a verdict of at least $100 million, or at least 2% of the company's stock-market value (market cap) the day before the verdict, so small companies are included too."
    )
    w(
        f"- **What we found:** {len(cases)} verdicts and {len(rows)} company rows (a verdict between two listed companies gets one row per company), covering {len(tickers)} different stocks."
    )
    w(
        f"- **The headline:** most verdicts barely moved the stock. The typical (median) move against the market was {med * 100:.1f}%. Only {over[0.10]} of {len(absm)} priced rows moved more than 10%, mostly smaller companies where the award was a large share of the company's value.{confound}"
    )
    w(
        "- **On speed:** jury verdicts are poor material for a fast-alert strategy. The trial date is public, the verdict is read aloud in a courtroom, and no free source records the minute it happened. The better targets are the judges' and appeals courts' later rulings that cut or erase verdicts, which arrive on unannounced days."
    )
    w(
        '- **Still open:** filing dates, trial start and end dates, and court docket numbers are blank for most rows. Prices are missing for some over-the-counter and delisted stocks. See "What is missing".\n'
    )

    w("## How the list was built\n")
    w(
        "- **No official register exists.** US courts do not publish a free list of verdicts. So we combined several free sources and checked each case by hand."
    )
    w(
        "- **Year-end lists:** TopVerdict publishes the 100 largest verdicts each year and the largest by category (patent, product liability and so on). We read the 2021 to 2025 lists, about 670 entries, and matched the defendants and plaintiffs to listed companies."
    )
    w(
        '- **Company filings:** listed companies must tell investors about material lawsuits. We ran SEC full-text searches of 8-K (current event), 10-Q and 10-K (quarterly and annual) filings for phrases like "jury verdict" and "jury awarded", which returned about 4,800 filings, and read the passages that named a verdict amount.'
    )
    w(
        "- **News:** Google News searches confirmed each verdict's date, amount and parties, and found later events such as appeals."
    )
    w(
        "- **CourtListener:** the free court-records site was not used in the end. Its free quota (about 125 requests a day) is shared with other projects and was used up during this build, so no row depends on it, and docket numbers and filing dates are still blank."
    )
    w(
        "- **Hand check:** every row was matched to at least one dated report of the verdict itself. Rows marked high confidence also match the company's own SEC filing. Medium means news reports agree but the court record itself was not read. Low means a key detail, such as the exact day or the court, is still unconfirmed.\n"
    )

    w("## How stock moves were measured\n")
    w(
        "- **Return:** the percentage change in the closing price from one trading day to the next."
    )
    w(
        "- **Abnormal return:** the stock's return minus the return of the overall market on the same days, measured by the SPY index fund, or the XBI biotech fund for drug companies. This strips out moves that had nothing to do with the case."
    )
    w(
        "- **Two-day window:** a verdict can come in the morning, the afternoon or after the market closes, and the free reports almost never say which. So the decision-day move is the two-day move covering the verdict day and the next trading day."
    )
    w(
        "- **Prices:** daily closes come from the Nasdaq public quote API and Polygon, because Yahoo Finance was refusing requests from this machine during the build. Nasdaq closes adjust for stock splits but not dividends, which adds a small error on the few days a dividend is paid.\n"
    )

    w("## Counts\n")
    w("**Verdicts per year**\n")
    for y in sorted(years):
        w(
            f"- {y}: {len(years[y])}{' (to mid-October)' if y == str(TODAY.year) else ''}"
        )
    w("")
    w("**Who was on which side**\n")
    w(
        f"- Listed company was the defendant: {sum(r['company_role'] == 'defendant' for r in rows)} rows."
    )
    w(
        f"- Listed company was the plaintiff: {sum(r['company_role'] == 'plaintiff' for r in rows)} rows."
    )
    w(
        f"- Verdicts under $100 million that qualify only because they were at least 2% of the company's value: {len(under100)} rows."
    )
    w(f"- Rows where the award was at least 2% of market cap: {len(small)}.\n")
    w("**Outcomes**\n")
    w(
        f"- Good for the listed company: {ofc['good']} rows. Bad: {ofc['bad']}. Mixed: {ofc['mixed']}."
    )
    w(
        "- By the case's current status: "
        + ", ".join(f"{k} {v}" for k, v in sorted(outc.items()))
        + '. "Loss" means the company lost at trial; "settled" means the parties settled after the verdict.'
    )
    w(
        "- Many large awards were later cut or thrown out by the trial judge or an appeals court. These later events are in each row's notes with dates.\n"
    )

    w("## How much the stock moved\n")
    w(f"- **Rows with a measured move:** {len(absm)} of {len(rows)}.")
    w(f"- **Moved more than 5% against the market:** {over[0.05]}.")
    w(f"- **More than 10%:** {over[0.10]}.")
    w(f"- **More than 25%:** {over[0.25]}.")
    w(
        f"- **Median absolute abnormal move:** {med * 100:.1f}%. Half the rows moved less than this, in either direction.\n"
    )
    w("**The 10 biggest moves**\n")
    for m, r in moved[:10]:
        share = (
            f", {float(r['revenue_at_stake_share']) * 100:.0f}% of market cap"
            if r["revenue_at_stake_share"]
            else ""
        )
        amt = (
            f"${float(r['revenue_at_stake_usd']) / 1e6:,.0f}M"
            if r["revenue_at_stake_usd"]
            else "award n/a"
        )
        w(
            f"- **{r['company']} ({r['ticker']}), {r['decision_date']}:** {pct(float(r['abn_ret_decision_day']))}. {r['case_name']}; {r['company_role']}; {amt}{share}."
            + (
                " Earnings came out in the same window, so this is not the verdict alone."
                if "CAUTION" in r["notes"]
                else ""
            )
        )
    w("")
    w(
        "The pattern is plain. Big companies shrug off even billion-dollar verdicts, because investors expect appeals to cut them and the sums are small next to the company's value. Intel lost $2.18 billion in 2021 and fell about 3% against the market. The large moves came where the award was a big slice of a small company.\n"
    )

    w("## Which outcomes can be traded on fast\n")
    w(
        "The model case for this project is Liquidia: a court posted an order at 11:15 a.m., during market hours, on a day nobody knew in advance, and the company's own press release came about two hours later. The question is how many cases in this list look like that."
    )
    w("")
    w(
        f"- **Published during market hours with no preset date:** {len(open_fast)}. Every row here is a jury verdict at the end of a trial whose start date was public, so none qualifies as unscheduled. The day of the verdict is uncertain, but only within a trial window everyone can see."
    )
    w(
        f'- **Exact time of the verdict:** found for {sum(r["time_precision"] == "minute" for r in rows)} rows. Verdicts are read aloud in court. The first public source is the courtroom, then reporters (Law360, Reuters, Bloomberg Law). The free news feeds give only the day, so time precision is "day" throughout.'
    )
    w(
        f"- **Median lead over the company's own release:** {statistics.median(leads) if leads else 'not measurable'}{' minutes' if leads else ''}. This needs a minute-level time for both the verdict and the company's release; we have the second but not the first."
    )
    w(
        f"- **Median minutes to half the move:** {statistics.median(halves) if halves else 'not measurable'}. This needs both the minute of the news and one-minute price bars. Polygon's free plan has those bars for about the last two years, which covers {minute_ok} rows, but without a news time there is no starting point."
    )
    w(
        f"- **Company releases:** {len(rel)} rows have an 8-K filing about the verdict, timed from EDGAR's acceptance stamp. {len(rel_open)} of those were filed while the market was open; most came after the close or days later."
    )
    w("")
    w("**The 10 best examples**\n")
    w(
        "The rulings that fit the Liquidia pattern are not the verdicts themselves but what judges and appeals courts did to them afterwards. A judge can rule on a post-trial motion any day, and appeals courts post opinions without notice. Below are the ten largest stock moves around those rulings, measured as the two-day abnormal move covering the day of the first report and the day before. The time of day was not found in free sources, so these are candidates for a live alert, not proven fast trades.\n"
    )
    for _, line in pt_lines[:10]:
        w(line)
    w("")
    w(
        "Most of these moves are small, and several go the wrong way: Intel fell when its $2.18 billion loss was thrown out, and Gen Digital fell when its judgment was reversed. Over two days, other news drowns out a ruling that a big company had already priced in. The clearest case is Pegasystems, a mid-sized company facing a verdict worth about 70% of its value, which rose 6.2% against the market when the appeals court threw the verdict out. That is the profile worth an alert: a pending post-trial or appeal ruling on an award that is large next to the company.\n"
    )

    w("## What is missing\n")
    w(
        "- **Verdicts we probably missed:** the TopVerdict lists stop at about 100 verdicts a year, and 2026 has no list yet, so 2026 relies on company filings and news. Our rough estimate, not a measurement, is that we have 80 to 90% of verdicts over $100 million and perhaps half of the smaller ones that qualify only under the 2% rule. Those smaller cases rarely make year-end lists, and small companies do not always file an 8-K."
    )
    w(
        "- **Who counts as listed:** verdicts against private subsidiaries are booked to the listed parent (Monsanto to Bayer, Philip Morris USA to Altria). Bayer, Fannie Mae, Freddie Mac and Netlist trade over the counter rather than on an exchange; they are kept but most have no free price history."
    )
    w(
        f"- **Missing prices:** {len(noprice)} rows have no measured move, mostly over-the-counter stocks, delisted stocks, and stocks the Nasdaq quote API does not carry."
    )
    w(
        "- **Facts at filing:** the date each lawsuit was filed, the trial dates and the docket numbers are blank for most rows. Collecting them needs about two pages of court records per case, which the shared CourtListener quota does not allow in one session. Market cap at filing is therefore blank; the notes give market cap the day before the verdict instead."
    )
    w(
        "- **Defense verdicts left out:** this list counts awards of money. Trials where the company won outright, so that no money was awarded, are not here, though they move stocks too."
    )
    w(
        "- **Option prices:** the market's expected move before a verdict (from option prices) is blank. Free historical option data mostly does not exist for these dates.\n"
    )
    w("## Bottom line\n")
    w(
        "For most listed companies a jury verdict, even a huge one, is a non-event for the stock. The verdicts that matter are the ones that are large relative to a small company, and the later rulings that cut or erase them. If Peter wants a fast alert, the better place to look is post-trial and appeals rulings in cases already on this list, not the verdicts themselves.\n"
    )
    w(
        "_This is historical research, not investment advice. Rows marked medium or low confidence have not been checked against the court record._"
    )
    (ROOT / "docs" / "universe_jury_verdict.md").write_text("\n".join(L) + "\n")
    print("wrote docs/universe_jury_verdict.md")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    stage = sys.argv[1] if len(sys.argv) > 1 else "build"
    if stage == "topverdict":
        print(len(topverdict()))
    elif stage == "efts":
        print(len(efts_hits()))
    elif stage == "news":
        print(len(news()))
    elif stage == "snippets":
        snippets()
    elif stage == "build":
        build()
        report()
    elif stage == "report":
        report()
