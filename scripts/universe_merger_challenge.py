"""Every US government lawsuit to block a merger, 2021-01-01 to today, with stock moves.

Stages (run in order; each caches raw downloads under data/universe/merger_challenge/raw/):
  python3 scripts/universe_merger_challenge.py sources   # agency listings -> raw/source_*_listing.csv
  python3 scripts/universe_merger_challenge.py build     # CASES + prices + SEC -> cases.csv

Sources:
- FTC Legal Library, Competition > Merger filter. ftc.gov answers plain HTTP clients with
  404, so pages are loaded in the local Chrome over CDP (http://localhost:29229).
- DOJ Antitrust Division "Antitrust Case Filings", Civil Merger filter. justice.gov answers
  401 to scripts and to the browser, so we read the Internet Archive's copies.
- Cases themselves (CASES below) were curated by hand from those listings, agency press
  releases, court dockets and the companies' 8-Ks; every source is in the row.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "merger_challenge"
RAW = OUT / "raw"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
WEB_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0 Safari/537.36"
)
_last: dict[str, float] = {}
_GAP = {"sec.gov": 0.15, "web.archive.org": 1.0, "courtlistener.com": 13.0}


def _key(sub: str, url: str) -> Path:
    d = RAW / sub
    d.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(url.encode()).hexdigest()[:12]
    return d / (re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + "_" + digest + ".txt")


def get(
    url: str, sub: str = "misc", tries: int = 4, headers: dict | None = None
) -> str:
    """GET with an on-disk cache; '' on failure. Never re-requests a cached URL."""
    key = _key(sub, url)
    if key.exists():
        return key.read_text()
    host = urllib.parse.urlparse(url).hostname or ""
    h = {"User-Agent": SEC_UA if host.endswith("sec.gov") else WEB_UA}
    h.update(headers or {})
    if host.endswith("courtlistener.com"):
        import os

        tok = os.environ.get("COURTLISTENER_API_TOKEN")
        if tok:
            h["Authorization"] = f"Token {tok}"
    for i in range(tries):
        for k, gap in _GAP.items():
            if host.endswith(k):
                wait = _last.get(k, 0) + gap - time.time()
                if wait > 0:
                    time.sleep(wait)
                _last[k] = time.time()
        try:
            r = requests.get(url, headers=h, timeout=90)
        except requests.RequestException:
            time.sleep(5 * (i + 1))
            continue
        if r.status_code == 200:
            key.write_text(r.text)
            return r.text
        if r.status_code in (202, 429, 500, 502, 503, 504):
            time.sleep(10 * (i + 1))
            continue
        return ""
    return ""


def text_of(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"<[^>]+>", "\n", h)
    return re.sub(r"\n\s*\n+", "\n", html.unescape(h))


# ---------------------------------------------------------------- FTC (Chrome over CDP)
FTC_LIST = (
    "https://www.ftc.gov/legal-library/browse/cases-proceedings?"
    "field_mission%5B30%5D=30&field_competition_topics=708&items_per_page=100&page={p}"
)


def chrome_pages(urls: list[str], sub: str) -> dict[str, str]:
    """Load pages in the local Chrome (CDP) and cache their HTML."""
    out, todo = {}, []
    for u in urls:
        k = _key(sub, u)
        if k.exists():
            out[u] = k.read_text()
        else:
            todo.append(u)
    if not todo:
        return out
    import asyncio

    from playwright.async_api import async_playwright

    async def run():
        async with async_playwright() as p:
            b = await p.chromium.connect_over_cdp("http://localhost:29229")
            pg = await b.contexts[0].new_page()
            for u in todo:
                try:
                    r = await pg.goto(u, wait_until="domcontentloaded", timeout=90000)
                    await pg.wait_for_timeout(1500)
                    if r and r.status == 200:
                        h = await pg.content()
                        _key(sub, u).write_text(h)
                        out[u] = h
                    else:
                        print("chrome", r.status if r else None, u, file=sys.stderr)
                except Exception as e:  # noqa: BLE001
                    print("chrome error", u, e, file=sys.stderr)
                await asyncio.sleep(1.0)
            await pg.close()

    asyncio.run(run())
    return out


def ftc_listing() -> list[dict]:
    rows = []
    for p in range(12):
        u = FTC_LIST.format(p=p)
        h = chrome_pages([u], "ftc").get(u, "")
        arts = re.findall(
            r'<article about="([^"]+)" class="node node--type-case.*?</article>',
            h,
            re.DOTALL,
        )
        bodies = re.findall(
            r'(<article about="[^"]+" class="node node--type-case.*?</article>)',
            h,
            re.DOTALL,
        )
        if not arts:
            break
        for a, b in zip(arts, bodies, strict=True):
            t = text_of(b)
            title = re.search(r'class="node-title"><a[^>]*>(.*?)</a>', b, re.DOTALL)
            upd = re.search(r'Last Updated.*?datetime="([\d-]+)', b, re.DOTALL)
            typ = re.search(r"Type of Action\s*\n\s*(.+)", t)
            mat = re.search(r"Matter/File Number\s*\n\s*(.+)", t)
            st = re.search(r"Case Status\s*\n\s*(.+)", t)
            body = re.search(r"field--name-body.*?</div>\s*</div>", b, re.DOTALL)
            rows.append(
                {
                    "agency": "FTC",
                    "title": html.unescape(title.group(1)).strip() if title else "",
                    "url": "https://www.ftc.gov" + a,
                    "action_type": typ.group(1).strip() if typ else "",
                    "matter": mat.group(1).strip() if mat else "",
                    "status": st.group(1).strip() if st else "",
                    "last_updated": upd.group(1) if upd else "",
                    "summary": re.sub(r"\s+", " ", text_of(body.group(0)))[:1500]
                    if body
                    else "",
                }
            )
    return rows


# ---------------------------------------------------------------- DOJ (Internet Archive)
DOJ_LIST = (
    "http://web.archive.org/web/{ts}/https://www.justice.gov/atr/antitrust-case-filings?"
    "f%5B0%5D=cases_index_list_case_type%3Acivil_merger&page={p}"
)


def _doj_parse(h: str) -> list[dict]:
    rows = []
    pat = re.compile(
        r'<a href="(?:/web/\d+/)?(https://www\.justice\.gov/atr/case/[^"]+)"[^>]*>(.*?)</a>(.{0,3000}?)'
        r"Case Open Date.*?([A-Z][a-z]+ \d{1,2}, \d{4}).*?Case Type.*?>\s*([A-Za-z ]+?)\s*<",
        re.DOTALL,
    )
    for m in pat.finditer(h):
        court = re.search(
            r"Federal Court.*?<div[^>]*>\s*([^<]+)",
            h[m.end() : m.end() + 800],
            re.DOTALL,
        )
        rows.append(
            {
                "agency": "DOJ",
                "title": re.sub(
                    r"\s+", " ", html.unescape(re.sub("<[^>]+>", "", m.group(2)))
                ).strip(),
                "open_date": datetime.strptime(m.group(4), "%B %d, %Y")
                .date()
                .isoformat(),
                "case_type": m.group(5).strip(),
                "court": court.group(1).strip() if court else "",
                "url": m.group(1),
            }
        )
    return rows


def doj_listing() -> list[dict]:
    rows = []
    for p in range(60):
        h = get(DOJ_LIST.format(ts="20250210", p=p), "doj")
        got = _doj_parse(h) if h else []
        if not got:
            break
        rows += got
        if min(g["open_date"] for g in got) < "2021-01-01":
            break
    # Newer filings (after Feb 2025): the all-types listing archived in 2026, by year
    for yr in ("2025", "2026"):
        for p in range(5):
            u = (
                "http://web.archive.org/web/2026/https://www.justice.gov/atr/antitrust-case-filings?"
                f"f%5B0%5D=cases_index_list_date%3A{yr}" + (f"&page={p}" if p else "")
            )
            h = get(u, "doj")
            got = _doj_parse(h) if h else []
            rows += [g for g in got if "Merger" in g["case_type"]]
            if len(got) < 10:
                break
    seen, out = set(), []
    for r in rows:
        k = (r["title"], r["open_date"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def sources() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ftc = ftc_listing()
    doj = doj_listing()
    print("FTC merger case pages:", len(ftc), " DOJ civil merger cases:", len(doj))
    with open(RAW / "source_ftc_listing.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ftc[0]))
        w.writeheader()
        w.writerows(ftc)
    with open(RAW / "source_doj_listing.csv", "w", newline="") as f:
        cols = ["agency", "title", "open_date", "case_type", "court", "url"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(doj, key=lambda r: r["open_date"], reverse=True))


# ---------------------------------------------------------------------------
# BUILD: hand-curated case list, then prices, SEC facts and timing.
# ---------------------------------------------------------------------------

FTC_PR = "https://www.ftc.gov/news-events/news/press-releases/"
DOJ_CASE = "https://www.justice.gov/atr/case/"


def P(
    ticker,
    company,
    role,
    cp="",
    cpt="",
    deal=None,
    ofc="unknown",
    bench="SPY",
    note="",
    price=None,
):
    """One listed party. deal = deal value in USD; price = cash deal price per target share."""
    return {
        "ticker": ticker,
        "company": company,
        "role": role,
        "cp": cp,
        "cpt": cpt,
        "deal": deal,
        "ofc": ofc,
        "bench": bench,
        "note": note,
        "price": price,
    }


# fmt: off
CASES = [
    {"id": "mc_2021_aon_wtw", "name": "U.S. v. Aon plc and Willis Towers Watson plc", "agency": "DOJ",
         "court": "D.D.C.", "filed": "2021-06-16", "decision": "2021-07-26", "known": "no", "outcome": "withdrawn",
         "dsrc": "https://www.justice.gov/opa/pr/aon-and-willis-towers-watson-abandon-merger-after-justice-department-sues",
         "q": "Aon Willis Towers Watson terminate merger", "conf": "medium",
         "events": "2021-07-26 companies terminated the deal before the scheduled trial; DOJ then dismissed the suit.",
         "src": DOJ_CASE + "us-v-aon-plc-and-willis-towers-watson-plc",
         "parties": [P("AON", "Aon plc", "acquirer", "Willis Towers Watson", "WTW", 30e9, "bad",
                    note="All-stock deal: 1.08 Aon shares per WTW share."),
                  P("WTW", "Willis Towers Watson plc", "target", "Aon plc", "AON", 30e9, "bad",
                    note="All-stock deal: 1.08 Aon shares per WTW share; deal value about $30B.")]},
    {"id": "mc_2021_prh_ss", "name": "U.S. v. Bertelsmann SE & Co. KGaA, Penguin Random House, ViacomCBS and Simon & Schuster",
         "agency": "DOJ", "court": "D.D.C.", "filed": "2021-11-02", "trial": ("2022-08-01", "2022-08-19"),
         "decision": "2022-10-31", "known": "no", "outcome": "loss",
         "dsrc": "https://www.justice.gov/opa/pr/justice-department-obtains-permanent-injunction-blocking-penguin-random-house-s-proposed",
         "q": "judge blocks Penguin Random House Simon & Schuster", "conf": "medium",
         "events": "2022-11-21 Paramount terminated the sale; Simon & Schuster later sold to KKR.",
         "src": DOJ_CASE + "us-v-bertelsmann-se-co-kgaa-et-al",
         "parties": [P("PARA", "Paramount Global (ViacomCBS)", "target", "Penguin Random House (Bertelsmann, not US-listed)", "",
                    2.175e9, "bad", note="Paramount was the seller of Simon & Schuster for $2.175B cash; "
                    "row is the listed parent of the target business.")]},
    {"id": "mc_2022_unh_chng", "name": "U.S., Minnesota and New York v. UnitedHealth Group and Change Healthcare",
         "agency": "DOJ", "court": "D.D.C.", "filed": "2022-02-24", "trial": ("2022-08-01", "2022-08-19"),
         "decision": "2022-09-19", "known": "no", "outcome": "win",
         "dsrc": "https://www.justice.gov/atr/case/us-et-al-v-unitedhealth-group-inc-and-change-healthcare-inc",
         "q": "judge UnitedHealth Change Healthcare ruling", "conf": "medium",
         "events": "2022-10-03 deal closed; DOJ appealed then dropped the appeal 2023-03-20.",
         "src": DOJ_CASE + "us-et-al-v-unitedhealth-group-inc-and-change-healthcare-inc",
         "parties": [P("UNH", "UnitedHealth Group", "acquirer", "Change Healthcare", "CHNG", 13e9, "good"),
                  P("CHNG", "Change Healthcare", "target", "UnitedHealth Group", "UNH", 13e9, "good", price=25.75,
                    note="$25.75 cash per share; about $13B including debt.")]},
    {"id": "mc_2022_bah_everwatch", "name": "U.S. v. Booz Allen Hamilton Holding Corp. et al. (EverWatch)", "agency": "DOJ",
         "court": "D. Md.", "filed": "2022-06-29", "decision": "2022-09-23", "known": "no", "outcome": "win",
         "dsrc": "https://www.justice.gov/atr/case/us-v-booz-allen-hamilton-holding-corp-et-al",
         "q": "judge Booz Allen EverWatch injunction", "conf": "medium",
         "events": "Preliminary injunction denied 2022-09-23; DOJ dismissed 2022-10.",
         "src": DOJ_CASE + "us-v-booz-allen-hamilton-holding-corp-et-al",
         "parties": [P("BAH", "Booz Allen Hamilton", "acquirer", "EverWatch (private)", "", 440e6, "good")]},
    {"id": "mc_2022_assa_hhi", "name": "U.S. v. Assa Abloy AB and Spectrum Brands Holdings", "agency": "DOJ", "court": "D.D.C.",
         "filed": "2022-09-15", "trial": ("2023-04-25", "2023-05-05"), "decision": "2023-05-05", "known": "no", "outcome": "settled",
         "dsrc": "https://www.justice.gov/opa/pr/justice-department-requires-divestitures-assa-abloy-s-acquisition-spectrum-brands-hardware-and-home",
         "q": "Assa Abloy Spectrum Brands settlement Justice Department", "conf": "medium",
         "events": "Settled mid-trial 2023-05-05 with divestitures; sale closed 2023-06-20.",
         "src": DOJ_CASE + "us-v-assa-abloy-ab-et-al",
         "parties": [P("SPB", "Spectrum Brands Holdings", "target", "Assa Abloy (Sweden, OTC only)", "", 4.3e9, "good",
                    note="Spectrum was the seller of its Hardware & Home Improvement unit for $4.3B cash.")]},
    {"id": "mc_2023_jblu_save", "name": "U.S. et al. v. JetBlue Airways Corp. and Spirit Airlines", "agency": "DOJ",
         "court": "D. Mass.", "filed": "2023-03-07", "trial": ("2023-10-31", "2023-12-05"), "decision": "2024-01-16", "known": "no",
         "outcome": "loss", "dsrc": "https://www.justice.gov/opa/pr/statement-attorney-general-merrick-b-garland-court-decision-block-jetblue-spirit-merger",
         "q": "judge blocks JetBlue Spirit merger", "conf": "medium",
         "events": "2024-03-04 companies terminated the deal.",
         "src": DOJ_CASE + "us-et-al-v-jetblue-airways-corporation-and-spirit-airlines-inc",
         "parties": [P("JBLU", "JetBlue Airways", "acquirer", "Spirit Airlines", "SAVE", 3.8e9, "bad"),
                  P("SAVE", "Spirit Airlines", "target", "JetBlue Airways", "JBLU", 3.8e9, "bad", price=33.50,
                    note="$33.50 cash per share at filing ($31.00 plus prepayments); deal value $3.8B.")]},
    {"id": "mc_2024_unh_amed", "name": "U.S. and Plaintiff States v. UnitedHealth Group and Amedisys", "agency": "DOJ",
         "court": "D. Md.", "filed": "2024-11-12", "decision": "2025-08-07", "known": "no", "outcome": "settled",
         "dsrc": "https://www.justice.gov/atr/case/us-and-plaintiff-states-v-unitedhealth-group-inc-and-amedisys-inc",
         "q": "UnitedHealth Amedisys settlement Justice Department", "conf": "medium",
         "events": "Proposed settlement with 164 divestitures 2025-08-07; deal closed 2025-08-14; final judgment 2025-12.",
         "src": DOJ_CASE + "us-and-plaintiff-states-v-unitedhealth-group-inc-and-amedisys-inc",
         "parties": [P("UNH", "UnitedHealth Group", "acquirer", "Amedisys", "AMED", 3.3e9, "good"),
                  P("AMED", "Amedisys", "target", "UnitedHealth Group", "UNH", 3.3e9, "good", price=101.0,
                    note="$101 cash per share; deal value $3.3B.")]},
    {"id": "mc_2025_gbtg_cwt", "name": "U.S. v. Global Business Travel Group and CWT Holdings", "agency": "DOJ",
         "court": "S.D.N.Y.", "filed": "2025-01-10", "decision": "2025-07-29", "known": "no", "outcome": "dismissed",
         "dsrc": "https://www.justice.gov/atr/case/us-v-global-business-and-cwt",
         "q": "Justice Department drops Amex GBT CWT", "conf": "medium",
         "events": "DOJ voluntarily dismissed 2025-07-29, before a September trial; deal closed 2025-09.",
         "src": DOJ_CASE + "us-v-global-business-and-cwt",
         "parties": [P("GBTG", "Global Business Travel Group (Amex GBT)", "acquirer", "CWT (private)", "", 570e6, "good")]},
    {"id": "mc_2025_hpe_jnpr", "name": "U.S. v. Hewlett Packard Enterprise Co. and Juniper Networks", "agency": "DOJ",
         "court": "N.D. Cal.", "filed": "2025-01-30", "decision": "2025-06-28", "known": "no", "outcome": "settled",
         "dsrc": "https://www.justice.gov/opa/pr/justice-department-requires-divestiture-hewlett-packard-enterprises-acquisition-juniper",
         "q": "HPE Juniper settlement Justice Department", "conf": "medium",
         "events": "Settled Saturday 2025-06-28, about a week before trial; deal closed 2025-07-02; states sought Tunney Act review.",
         "src": "https://www.justice.gov/atr/case/us-v-hewlett-packard-enterprise-co-and-juniper-networks-inc",
         "parties": [P("HPE", "Hewlett Packard Enterprise", "acquirer", "Juniper Networks", "JNPR", 14e9, "good"),
                  P("JNPR", "Juniper Networks", "target", "Hewlett Packard Enterprise", "HPE", 14e9, "good", price=40.0,
                    note="$40 cash per share; deal value $14B.")]},
    {"id": "mc_2026_tdg_stellant", "name": "DOJ threatened suit: TransDigm / Stellant Systems", "agency": "DOJ",
         "court": "(no complaint filed)", "filed": "2026-07-13", "decision": "2026-07-13", "known": "no", "outcome": "withdrawn",
         "dsrc": "https://www.crainscleveland.com/manufacturing/doj-was-prepared-sue-transdigm-acquiring-competitor-stellant",
         "q": "TransDigm Stellant Justice Department", "conf": "low",
         "events": "TransDigm dropped the $960M deal after DOJ said it would sue; no complaint on file. "
                "Counted only as an abandonment after an announced challenge; filed_date = abandonment date.",
         "src": "https://www.crainscleveland.com/manufacturing/doj-was-prepared-sue-transdigm-acquiring-competitor-stellant",
         "parties": [P("TDG", "TransDigm Group", "acquirer", "Stellant Systems (private)", "", 960e6, "bad")]},
    {"id": "mc_2021_ilmn_grail", "name": "In the Matter of Illumina, Inc. and GRAIL, Inc. (FTC Dkt. 9401)", "agency": "FTC",
         "court": "FTC administrative (Part 3)", "docket": "9401", "filed": "2021-03-30", "trial": ("2021-08-24", "2021-09-23"),
         "decision": "2022-09-01", "known": "no", "outcome": "win",
         "dsrc": FTC_PR + "2022/09/administrative-law-judge-dismisses-ftcs-challenge-illuminas-proposed-acquisition-cancer-detection",
         "q": "judge dismisses FTC Illumina Grail", "conf": "medium",
         "events": "ALJ dismissed 2022-09-01; Commission reversed 2023-04-03 (ordered divestiture); 5th Cir. vacated 2023-12-15; "
                "Illumina said it would divest 2023-12-17. Federal PI suit (S.D. Cal.) dropped 2021-05.",
         "src": "https://www.ftc.gov/legal-library/browse/cases-proceedings/201-0144-illumina-inc-grail-inc-matter",
         "parties": [P("ILMN", "Illumina", "acquirer", "GRAIL (private)", "", 7.1e9, "good")]},
    {"id": "mc_2021_nvda_arm", "name": "In the Matter of Nvidia/Arm (FTC Dkt. 9404)", "agency": "FTC",
         "court": "FTC administrative (Part 3)", "docket": "9404", "filed": "2021-12-02", "decision": "2022-02-08", "known": "no",
         "outcome": "withdrawn", "dsrc": FTC_PR + "2022/02/statement-regarding-termination-nvidia-corps-attempted-acquisition-arm-ltd",
         "q": "Nvidia Arm deal terminated", "conf": "medium", "events": "Deal terminated 2022-02-08 (before market open, with SoftBank results).",
         "src": FTC_PR + "2021/12/ftc-sues-block-40-billion-semiconductor-chip-merger",
         "parties": [P("NVDA", "NVIDIA", "acquirer", "Arm Ltd (SoftBank, not US-listed)", "", 40e9, "bad")]},
    {"id": "mc_2022_lmt_ajrd", "name": "In the Matter of Lockheed Martin / Aerojet Rocketdyne (FTC Dkt. 9405)", "agency": "FTC",
         "court": "FTC administrative (Part 3)", "docket": "9405", "filed": "2022-01-25", "decision": "2022-02-13", "known": "no",
         "outcome": "withdrawn", "dsrc": FTC_PR + "2022/02/statement-regarding-termination-lockheed-martin-corporations-attempted-acquisition-aerojet",
         "q": "Lockheed Aerojet terminate", "conf": "medium", "events": "Lockheed terminated the deal Sunday 2022-02-13.",
         "src": FTC_PR + "2022/01/ftc-sues-block-lockheed-martin-corporations-44-billion-vertical-acquisition-aerojet-rocketdyne",
         "parties": [P("LMT", "Lockheed Martin", "acquirer", "Aerojet Rocketdyne", "AJRD", 4.4e9, "bad"),
                  P("AJRD", "Aerojet Rocketdyne", "target", "Lockheed Martin", "LMT", 4.4e9, "bad", price=51.0,
                    note="$56 per share less a $5 special dividend already paid = $51 cash; deal value $4.4B.")]},
    {"id": "mc_2022_hca_steward", "name": "FTC v. HCA Healthcare and Steward Health Care System (Utah hospitals)", "agency": "FTC",
         "court": "D. Utah + FTC Part 3", "filed": "2022-06-02", "decision": "2022-06-17", "known": "no", "outcome": "withdrawn",
         "dsrc": "https://www.fiercehealthcare.com/providers/ftc-notches-another-antitrust-win-hca-healthcare-steward-health-care-call-5-hospital-sale",
         "q": "HCA Steward Utah hospitals", "conf": "medium",
         "events": "Temporary restraining order 2022-06-08; parties called off the five-hospital sale about 2022-06-17 (date from press reports).",
         "src": FTC_PR + "2022/06/ftc-sues-block-merger-between-utah-healthcare-rivals-hca-healthcare-steward-health-care-system",
         "parties": [P("HCA", "HCA Healthcare", "acquirer", "Steward Health Care (private)", "", None, "bad",
                    note="Price of the five Utah hospitals not disclosed.")]},
    {"id": "mc_2022_meta_within", "name": "FTC v. Meta Platforms, Mark Zuckerberg and Within Unlimited", "agency": "FTC",
         "court": "N.D. Cal.", "filed": "2022-07-27", "trial": ("2022-12-08", "2022-12-20"), "decision": "2023-02-01", "known": "no",
         "outcome": "win", "dsrc": "https://www.nytimes.com/2023/02/01/technology/meta-within-ftc-ruling.html",
         "q": "judge Meta Within FTC", "conf": "medium",
         "events": "Sealed order denying the injunction reported 2023-02-01; public opinion 2023-02-03; FTC dropped Part 3 case 2023-02-24.",
         "src": "https://www.ftc.gov/legal-library/browse/cases-proceedings/meta-platformsmark-zuckerbergwithin-unlimited-ftc-v",
         "parties": [P("META", "Meta Platforms", "acquirer", "Within Unlimited (private)", "", 400e6, "good",
                    note="Price not disclosed by Meta; about $400M per press reports (estimate).")]},
    {"id": "mc_2022_msft_atvi", "name": "FTC v. Microsoft Corp. and Activision Blizzard (Part 3 Dkt. 9412; N.D. Cal. PI suit)",
         "agency": "FTC", "court": "N.D. Cal. + FTC Part 3", "docket": "9412", "filed": "2022-12-08", "trial": ("2023-06-22", "2023-06-29"),
         "decision": "2023-07-11", "known": "no", "outcome": "win",
         "dsrc": "https://www.nytimes.com/2023/07/11/technology/microsoft-activision-ftc-ruling.html",
         "q": "judge Microsoft Activision FTC ruling", "conf": "medium",
         "events": "Part 3 complaint 2022-12-08; federal injunction suit 2023-06-12; injunction denied 2023-07-11; deal closed 2023-10-13.",
         "src": "https://www.ftc.gov/legal-library/browse/cases-proceedings/2210077-microsoftactivision-blizzard-matter",
         "parties": [P("MSFT", "Microsoft", "acquirer", "Activision Blizzard", "ATVI", 68.7e9, "good"),
                  P("ATVI", "Activision Blizzard", "target", "Microsoft", "MSFT", 68.7e9, "good", price=95.0,
                    note="$95 cash per share; deal value $68.7B.")]},
    {"id": "mc_2023_ice_bki", "name": "In the Matter of Intercontinental Exchange / Black Knight (FTC Dkt. 9413)", "agency": "FTC",
         "court": "FTC Part 3 + S.D.N.Y.", "docket": "9413", "filed": "2023-03-09", "decision": "2023-08-07", "known": "no",
         "outcome": "settled", "dsrc": "https://www.ftc.gov/legal-library/browse/cases-proceedings/intercontinental-exchange-incblack-knight-inc-matter",
         "q": "FTC ICE Black Knight settlement", "conf": "medium",
         "events": "Consent with divestitures (Optimal Blue, Empower) 2023-08-07; deal closed 2023-09-05.",
         "src": FTC_PR + "2023/03/ftc-acts-block-deal-combining-two-top-mortgage-loan-technology-providers",
         "parties": [P("ICE", "Intercontinental Exchange", "acquirer", "Black Knight", "BKI", 11.7e9, "good"),
                  P("BKI", "Black Knight", "target", "Intercontinental Exchange", "ICE", 11.7e9, "good", price=75.0,
                    note="Terms revised 2023-03-07 to $75 per share (about 90% cash); deal value about $11.7B.")]},
    {"id": "mc_2023_amgn_hznp", "name": "FTC et al. v. Amgen Inc. and Horizon Therapeutics", "agency": "FTC", "court": "N.D. Ill.",
         "filed": "2023-05-16", "decision": "2023-09-01", "known": "no", "outcome": "settled",
         "dsrc": FTC_PR + "2023/09/biopharmaceutical-giant-amgen-settle-ftc-state-challenges-its-horizon-therapeutics-acquisition",
         "q": "Amgen Horizon FTC settle", "conf": "medium",
         "events": "Hearing had been set for 2023-09-12; consent order 2023-09-01; deal closed 2023-10-06.",
         "src": FTC_PR + "2023/05/ftc-sues-block-biopharmaceutical-giant-amgen-acquisition-would-entrench-monopoly-drugs-used-treat",
         "parties": [P("AMGN", "Amgen", "acquirer", "Horizon Therapeutics", "HZNP", 27.8e9, "good", bench="XBI"),
                  P("HZNP", "Horizon Therapeutics", "target", "Amgen", "AMGN", 27.8e9, "good", bench="XBI", price=116.50,
                    note="$116.50 cash per share; deal value $27.8B.")]},
    {"id": "mc_2023_iqv_propel", "name": "FTC v. IQVIA Holdings and Propel Media", "agency": "FTC", "court": "S.D.N.Y.",
         "filed": "2023-07-17", "trial": ("2023-11-20", "2023-12-05"), "decision": "2023-12-29", "known": "no", "outcome": "loss",
         "dsrc": FTC_PR + "2024/01/statement-ftc-win-securing-temporary-block-iqvias-acquisition-propel-media",
         "q": "judge IQVIA Propel FTC injunction", "conf": "medium", "events": "IQVIA abandoned the deal 2024-01-05.",
         "src": FTC_PR + "2023/07/ftc-sues-block-iqvias-acquisition-propel-media-prevent-increased-concentration-health-care",
         "parties": [P("IQV", "IQVIA Holdings", "acquirer", "Propel Media (private)", "", None, "bad",
                    note="Price not disclosed.")]},
    {"id": "mc_2023_thc_johnmuir", "name": "FTC and California v. John Muir Health and Tenet Healthcare (San Ramon)", "agency": "FTC",
         "court": "N.D. Cal.", "filed": "2023-11-17", "decision": "2023-12-18", "known": "no", "outcome": "withdrawn",
         "dsrc": FTC_PR + "2023/12/statement-regarding-termination-john-muirs-takeover-san-ramon-regional-medical-center-tenet",
         "q": "John Muir San Ramon Tenet terminate", "conf": "medium", "events": "Parties ended the deal 2023-12-18.",
         "src": FTC_PR + "2023/11/ftc-sues-block-john-muir-healths-takeover-san-ramon-regional-medical-center",
         "parties": [P("THC", "Tenet Healthcare", "target", "John Muir Health (nonprofit)", "", 142e6, "bad",
                    note="Tenet was the seller of its 49% stake in San Ramon Regional for $142M.")]},
    {"id": "mc_2023_sny_maze", "name": "In the Matter of Sanofi / Maze Therapeutics", "agency": "FTC",
         "court": "FTC Part 3 + federal court", "filed": "2023-12-11", "decision": "2023-12-13", "known": "no", "outcome": "withdrawn",
         "dsrc": FTC_PR + "2023/12/statement-regarding-termination-sanofis-proposed-acquisition-maze-therapeutics-pompe-disease-drug",
         "q": "Sanofi Maze FTC", "conf": "medium", "events": "Sanofi dropped the license deal 2023-12-13.",
         "src": FTC_PR + "2023/12/ftc-seeks-block-sanofis-acquisition-rare-disease-drug-threatens-sanofis-monopoly",
         "parties": [P("SNY", "Sanofi (ADR)", "acquirer", "Maze Therapeutics (private)", "", 150e6, "bad", bench="XBI",
                    note="Exclusive license to a Pompe drug: $150M upfront plus milestones.")]},
    {"id": "mc_2024_cyh_novant", "name": "FTC v. Novant Health and Community Health Systems", "agency": "FTC", "court": "W.D.N.C.",
         "filed": "2024-01-25", "decision": "2024-05-16", "known": "no", "outcome": "win",
         "dsrc": FTC_PR + "2024/07/statement-regarding-termination-novant-healths-acquisition-hospitals-community-health-systems",
         "q": "judge Novant Community Health FTC injunction", "conf": "medium",
         "events": "District court denied the injunction 2024-05-16; 4th Cir. granted an injunction pending appeal 2024-06-?; "
                "Novant abandoned 2024-06-18.",
         "src": FTC_PR + "2024/01/ftc-sues-block-novant-healths-acquisition-two-hospitals-community-health-systems",
         "parties": [P("CYH", "Community Health Systems", "target", "Novant Health (nonprofit)", "", 320e6, "good",
                    note="CHS was the seller of two hospitals for $320M.")]},
    {"id": "mc_2024_kr_aci_ftc", "name": "FTC et al. v. The Kroger Company and Albertsons Companies", "agency": "FTC",
         "court": "D. Or.", "filed": "2024-02-26", "trial": ("2024-08-26", "2024-09-30"), "decision": "2024-12-10", "known": "no",
         "outcome": "loss", "dsrc": FTC_PR + "2024/12/statement-ftc-victory-securing-halt-kroger-albertsons-grocery-merger",
         "q": "judge blocks Kroger Albertsons", "conf": "medium",
         "events": "Washington state court blocked the deal the same day; Albertsons terminated 2024-12-11.",
         "src": FTC_PR + "2024/02/ftc-challenges-krogers-acquisition-albertsons",
         "parties": [P("KR", "Kroger", "acquirer", "Albertsons", "ACI", 24.6e9, "bad"),
                  P("ACI", "Albertsons Companies", "target", "Kroger", "KR", 24.6e9, "bad", price=34.10,
                    note="$34.10 cash per share at signing (less a $6.85 special dividend paid 2023-01); deal value $24.6B.")]},
    {"id": "mc_2024_kr_aci_wa", "name": "State of Washington v. Kroger and Albertsons", "agency": "State AG (WA)",
         "court": "King County Superior Court (WA)", "filed": "2024-01-15", "trial": ("2024-09-16", "2024-10-31"),
         "decision": "2024-12-10", "known": "no", "outcome": "loss",
         "dsrc": "https://www.atg.wa.gov/news/news-releases/ag-ferguson-wins-lawsuit-block-kroger-albertsons-merger",
         "q": "Washington judge Kroger Albertsons", "conf": "medium",
         "events": "Same day as the federal ruling; Albertsons terminated 2024-12-11.",
         "src": "https://www.atg.wa.gov/news/news-releases/ag-ferguson-files-lawsuit-block-kroger-albertsons-merger",
         "parties": [P("KR", "Kroger", "acquirer", "Albertsons", "ACI", 24.6e9, "bad"),
                  P("ACI", "Albertsons Companies", "target", "Kroger", "KR", 24.6e9, "bad", price=34.10,
                    note="$34.10 cash per share at signing; deal value $24.6B.")]},
    {"id": "mc_2024_kr_aci_co", "name": "State of Colorado v. Kroger and Albertsons", "agency": "State AG (CO)",
         "court": "Denver District Court (CO)", "filed": "2024-02-14", "trial": ("2024-09-30", "2024-10-24"),
         "decision": "2024-12-11", "known": "no", "outcome": "withdrawn",
         "dsrc": "https://coloradonewsline.com/2024/12/11/colorado-awaits-decision-kroger-albertsons/",
         "q": "Colorado Kroger Albertsons", "conf": "medium",
         "events": "No Colorado ruling before Albertsons ended the deal 2024-12-11 (after the federal and Washington rulings).",
         "src": "https://coag.gov/press-releases/2-14-24/",
         "parties": [P("KR", "Kroger", "acquirer", "Albertsons", "ACI", 24.6e9, "bad"),
                  P("ACI", "Albertsons Companies", "target", "Kroger", "KR", 24.6e9, "bad", price=34.10,
                    note="$34.10 cash per share at signing; deal value $24.6B.")]},
    {"id": "mc_2024_tpr_cpri", "name": "FTC v. Tapestry, Inc. and Capri Holdings", "agency": "FTC", "court": "S.D.N.Y.",
         "filed": "2024-04-22", "trial": ("2024-09-09", "2024-09-25"), "decision": "2024-10-24", "known": "no", "outcome": "loss",
         "dsrc": "https://www.ftc.gov/legal-library/browse/cases-proceedings/tapestry-capri",
         "q": "judge blocks Tapestry Capri", "conf": "medium", "events": "Companies terminated the deal 2024-11-14.",
         "src": FTC_PR + "2024/04/ftc-moves-block-tapestrys-acquisition-capri",
         "parties": [P("TPR", "Tapestry", "acquirer", "Capri Holdings", "CPRI", 8.5e9, "bad"),
                  P("CPRI", "Capri Holdings", "target", "Tapestry", "TPR", 8.5e9, "bad", price=57.0,
                    note="$57 cash per share; deal value $8.5B.")]},
    {"id": "mc_2024_tpx_mfrm", "name": "FTC v. Tempur Sealy International and Mattress Firm Group", "agency": "FTC",
         "court": "S.D. Tex.", "filed": "2024-07-02", "trial": ("2024-11-12", "2024-11-25"), "decision": "2025-01-31", "known": "no",
         "outcome": "win", "dsrc": "https://www.ftc.gov/legal-library/browse/cases-proceedings/tempur-sealy-international-inc-mattress-firm-group-inc-matter",
         "q": "judge Tempur Sealy Mattress Firm FTC", "conf": "medium", "events": "Deal closed 2025-02-05; FTC dropped its appeal.",
         "src": FTC_PR + "2024/07/ftc-moves-block-tempur-sealys-acquisition-mattress-firm",
         "parties": [P("SGI", "Somnigroup International (Tempur Sealy, ticker TPX at the time)", "acquirer", "Mattress Firm (private)", "", 4e9, "good")]},
    {"id": "mc_2025_srdx_gtcr", "name": "FTC v. GTCR BC Holdings and Surmodics", "agency": "FTC", "court": "N.D. Ill.",
         "filed": "2025-03-06", "decision": "2025-11-10", "known": "no", "outcome": "win",
         "dsrc": "https://www.reuters.com/legal/us-judge-rejects-ftcs-bid-block-private-equity-medical-company-deal-2025-11-10/",
         "q": "judge Surmodics GTCR FTC", "conf": "medium",
         "events": "Illinois and Minnesota joined 2025-04-17; deal closed 2025-11-19.",
         "src": FTC_PR + "2025/03/ftc-challenges-medical-device-coatings-deal",
         "parties": [P("SRDX", "Surmodics", "target", "GTCR (private equity)", "", 627e6, "good", price=43.0,
                    note="$43 cash per share; deal value $627M.")]},
    {"id": "mc_2025_ew_jena", "name": "FTC v. Edwards Lifesciences and JenaValve Technology", "agency": "FTC", "court": "D.D.C.",
         "filed": "2025-08-06", "decision": "2026-01-09", "known": "no", "outcome": "loss",
         "dsrc": FTC_PR + "2026/01/statement-ftc-victory-halting-anticompetitive-medical-device-deal",
         "q": "Edwards JenaValve judge FTC", "conf": "medium",
         "events": "Injunction granted 2026-01-09 after a six-day trial; Edwards abandoned 2026-01-10.",
         "src": FTC_PR + "2025/08/ftc-challenges-anticompetitive-medical-device-deal",
         "parties": [P("EW", "Edwards Lifesciences", "acquirer", "JenaValve (private)", "", 945e6, "bad")]},
    {"id": "mc_2025_z_rdfn", "name": "FTC v. Zillow Group and Redfin (rental-listings agreement)", "agency": "FTC",
         "court": "E.D. Va.", "filed": "2025-09-30", "decision": "2026-08-24", "known": "no", "outcome": "settled",
         "dsrc": FTC_PR + "2026/08/ftc-secures-order-resolving-antitrust-concerns-zillow-redfin-agreement",
         "q": "FTC Zillow Redfin settlement", "conf": "medium",
         "events": "Challenge to Zillow's $100M deal taking over Redfin's rental-ad business; complaint also alleged an illegal "
                "agreement, so this is a partial fit for the merger category.",
         "src": FTC_PR + "2025/09/ftc-sues-zillow-redfin-over-illegal-agreement-suppress-rental-advertising-competition",
         "parties": [P("Z", "Zillow Group", "acquirer", "Redfin (Rocket Companies)", "RKT", 100e6, "good"),
                  P("RKT", "Rocket Companies (Redfin parent)", "target", "Zillow Group", "Z", 100e6, "good",
                    note="Redfin, owned by Rocket since 2025-07, received $100M plus other pay.")]},
    {"id": "mc_2026_nxst_tgna", "name": "California et al. (8 states) v. Nexstar Media Group and TEGNA", "agency": "State AG (8 states)",
         "court": "E.D. Cal.", "filed": "2026-03-18", "decision": "2026-04-17", "known": "no", "outcome": "loss",
         "dsrc": "https://www.latimes.com/entertainment-arts/business/story/2026-04-17/judge-blocks-nexstar-tegna-deal",
         "q": "judge Nexstar Tegna injunction", "conf": "medium",
         "events": "Nexstar closed the deal 2026-03-19 anyway; TRO 2026-03-27 (hold separate); preliminary injunction 2026-04-17; "
                "Nexstar appealed; case pending.",
         "src": "https://oag.ca.gov/news/press-releases",
         "parties": [P("NXST", "Nexstar Media Group", "acquirer", "TEGNA", "TGNA", 6.2e9, "bad"),
                  P("TGNA", "TEGNA", "target", "Nexstar Media Group", "NXST", 6.2e9, "unknown", price=22.0,
                    note="$22 cash per share; deal value $6.2B. TEGNA delisted 2026-03-19, so no decision-day price.")]},
    {"id": "mc_2026_psky_wbd", "name": "California et al. (12 states) v. Paramount Skydance and Warner Bros. Discovery",
         "agency": "State AG (12 states)", "court": "(state AG suit; court to confirm)", "filed": "2026-07-13",
         "decision": "2026-09-21", "known": "no", "outcome": "settled",
         "dsrc": "https://www.cnbc.com/2026/09/21/paramount-warner-bros-state-attorneys-general-settle.html",
         "q": "Paramount Warner Bros attorneys general settle", "conf": "medium",
         "events": "Settlement 2026-09-21; court approval 2026-09-30.",
         "src": "https://www.nytimes.com/2026/07/13/business/states-sue-paramount-warner-bros.html",
         "parties": [P("PSKY", "Paramount Skydance", "acquirer", "Warner Bros. Discovery", "WBD", 111e9, "good"),
                  P("WBD", "Warner Bros. Discovery", "target", "Paramount Skydance", "PSKY", 111e9, "good", price=31.0,
                    note="$31 cash per share; enterprise value about $111B.")]},
]
# fmt: on

# CIKs for companies no longer in company_tickers.json (checked on EDGAR by name).
CIK_OVERRIDE: dict[str, int] = {
    "AJRD": 40888,
    "AMED": 896262,
    "ATVI": 718877,
    "BKI": 1627014,
    "CHNG": 1756497,
    "GBTG": 1820872,
    "HZNP": 1492426,
    "JNPR": 1043604,
    "SAVE": 1498710,
    "SRDX": 924717,
    "TGNA": 39899,
}


# ---------- prices ----------
def yahoo(sym: str) -> dict[str, tuple[float, float]]:
    """date -> (adjusted close, close*volume) from Yahoo's chart API."""
    p1, p2 = (
        int(datetime(2020, 6, 1).timestamp()),
        int(datetime(2026, 10, 14).timestamp()),
    )
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=div,split"
    t = get(u, "yahoo", headers={"User-Agent": "Mozilla/5.0"})
    try:
        r = json.loads(t)["chart"]["result"][0]
        first = r["meta"].get("firstTradeDate") or 0
        if first > p1 and len(r.get("timestamp", [])) < 300:
            # Yahoo silently switches to monthly bars when period1 predates the listing.
            u = u.replace(f"period1={p1}", f"period1={first}")
            r = json.loads(get(u, "yahoo", headers={"User-Agent": "Mozilla/5.0"}))[
                "chart"
            ]["result"][0]
        q = r["indicators"]["quote"][0]
        adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    except (ValueError, KeyError, TypeError, IndexError):
        return {}
    out = {}
    for ts, a, c, v in zip(r["timestamp"], adj, q["close"], q["volume"]):
        if a is None or c is None:
            continue
        d = datetime.fromtimestamp(ts, UTC).date().isoformat()
        out[d] = (a, c, (v or 0) * c)
    return out


_PX: dict[str, dict] = {}


def polygon_daily(sym: str) -> dict[str, tuple[float, float, float]]:
    """Fallback for delisted tickers: Polygon daily bars (free plan reaches back about 2 years)."""
    import os

    u = f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/{POLY_START}/2026-10-13?adjusted=true&limit=50000"
    path = _key("polygon", u)
    if path.exists():
        t = path.read_text()
    else:
        time.sleep(13)
        try:
            r = requests.get(
                u + "&apiKey=" + os.environ.get("POLYGON_API_KEY", ""), timeout=60
            )
            t = r.text if r.status_code == 200 else ""
        except requests.RequestException:
            t = ""
        if t:
            path.write_text(t)
    try:
        res = json.loads(t).get("results", [])
    except ValueError:
        return {}
    out = {}
    for b in res:
        d = datetime.fromtimestamp(b["t"] / 1000, UTC).date().isoformat()
        out[d] = (b["c"], b["c"], b["v"] * b["c"])
    return out


PX_SOURCE: dict[str, str] = {}


# Yahoo's PARA history after the 2025 Skydance merger is not Paramount Global's (closes near $97,800).
BAD_PX = {"PARA"}


def px(sym: str) -> dict:
    if sym in BAD_PX:
        PX_SOURCE[sym] = "none (Yahoo history is wrong for this old ticker)"
        return {}
    if sym not in _PX:
        _PX[sym] = yahoo(sym)
        PX_SOURCE[sym] = "Yahoo"
        if len(_PX[sym]) < 300 and sym not in ("SPY", "XBI"):
            # Yahoo drops delisted tickers and returns only a few recent bars for some renamed ones.
            poly = polygon_daily(sym)
            if len(poly) > len(_PX[sym]):
                _PX[sym] = poly
                PX_SOURCE[sym] = "Polygon daily"
            elif not _PX[sym]:
                PX_SOURCE[sym] = "none"
    return _PX[sym]


def cal() -> list[str]:
    return sorted(px("SPY"))


def eff_day(d: str, hhmm: str = "") -> str:
    """Trading day on which news published at date d, time hhmm (ET) first hits the close."""
    days = cal()
    i = next(k for k, x in enumerate(days) if x >= d)
    if days[i] == d and hhmm and hhmm >= "16:00":
        i += 1
    return days[i]


def ret(sym: str, d0: str, d1: str) -> float | None:
    """Close of the trading day before d0 to close of d1."""
    p, days = px(sym), cal()
    i0, i1 = days.index(d0) - 1, days.index(d1)
    a, b = p.get(days[i0]), p.get(days[i1])
    return round(b[0] / a[0] - 1, 4) if a and b else None


def shift(d: str, n: int) -> str:
    days = cal()
    return days[min(days.index(d) + n, len(days) - 1)]


# ---------- SEC ----------
def sec_json(u: str) -> dict:
    t = get(u, "sec")
    try:
        return json.loads(t)
    except ValueError:
        return {}


def cik_of(ticker: str) -> int | None:
    if ticker in CIK_OVERRIDE:
        return CIK_OVERRIDE[ticker]
    m = sec_json("https://www.sec.gov/files/company_tickers.json")
    for v in m.values():
        if v["ticker"] == ticker:
            return v["cik_str"]
    return None


def shares_out(facts: dict, asof: str) -> float | None:
    """dei cover-page share count (all classes) in the latest filing before asof;
    falls back to the balance-sheet us-gaap CommonStockSharesOutstanding."""
    f = facts.get("facts", {})
    for ns, tag in (
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    ):
        rows = f.get(ns, {}).get(tag, {}).get("units", {}).get("shares", [])
        rows = [r for r in rows if r["filed"] <= asof]
        if rows:
            last = max(r["filed"] for r in rows)
            last_end = max(r["end"] for r in rows if r["filed"] == last)
            return float(
                sum(
                    r["val"]
                    for r in rows
                    if r["filed"] == last and r["end"] == last_end
                )
            )
    return None


REV_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]


def ttm_revenue(facts: dict, asof: str) -> float | None:
    """Trailing-12-month revenue known at asof: latest 4 quarters (Q4 = annual minus Q1-Q3)."""
    best = None
    for tag in REV_TAGS:
        rows = (
            facts.get("facts", {})
            .get("us-gaap", {})
            .get(tag, {})
            .get("units", {})
            .get("USD", [])
        )
        rows = [r for r in rows if r["filed"] <= asof and "start" in r]
        if not rows:
            continue
        q, a = {}, {}
        for r in rows:
            n = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
            if 80 <= n <= 100:
                q[r["end"]] = r["val"]
            elif 350 <= n <= 380:
                a[r["end"]] = (r["start"], r["val"])
        for end, (start, val) in a.items():
            inside = [v for e, v in q.items() if start < e < end]
            if len(inside) == 3 and end not in q:
                q[end] = val - sum(inside)
        ends = sorted(q)[-4:]
        cand = None
        if (
            len(ends) == 4
            and (date.fromisoformat(ends[-1]) - date.fromisoformat(ends[0])).days < 300
        ):
            cand = (ends[-1], float(sum(q[e] for e in ends)))
        elif a:
            e = max(a)
            cand = (e, float(a[e][1]))
        if cand and (best is None or cand[0] > best[0]):
            best = cand
    return best[1] if best else None


def eight_ks(cik: int, d0: str, d1: str) -> list[dict]:
    """8-K/6-K filings accepted d0..d1: ET acceptance time, items, URL of the full submission text."""
    j = sec_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    blocks = [j.get("filings", {}).get("recent", {})]
    for f in j.get("filings", {}).get("files", []):
        if f["filingFrom"] <= d1 and f["filingTo"] >= d0:
            blocks.append(sec_json("https://data.sec.gov/submissions/" + f["name"]))
    out = []
    for b in blocks:
        for form, fd, acc, an, items in zip(
            b.get("form", []),
            b.get("filingDate", []),
            b.get("acceptanceDateTime", []),
            b.get("accessionNumber", []),
            b.get("items", []),
        ):
            if form in ("8-K", "6-K") and d0 <= fd <= d1:
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{an.replace('-', '')}/{an}.txt"
                out.append(
                    {"et": utc_to_et(acc[:19]), "items": items or "", "url": url}
                )
    return sorted(out, key=lambda x: x["et"])


def mentions(url: str, kw: str) -> bool:
    return kw.lower() in text_of(get(url, "sec")).lower()


def utc_to_et(s: str) -> str:
    from zoneinfo import ZoneInfo

    t = (
        datetime.fromisoformat(s)
        .replace(tzinfo=ZoneInfo("UTC"))
        .astimezone(ZoneInfo("America/New_York"))
    )
    return t.strftime("%Y-%m-%d %H:%M")


# ---------- news timing ----------
def news_first(q: str, d: str) -> tuple[str, str]:
    """Earliest Google News item about q published from d-1 18:00 ET to d+2 (ET)."""
    from email.utils import parsedate_to_datetime
    from zoneinfo import ZoneInfo

    u = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(q)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    x = get(u, "news")
    lo = datetime.fromisoformat(d) - timedelta(hours=6)
    hi = datetime.fromisoformat(d) + timedelta(days=2)
    best = None
    for t, pd_ in re.findall(
        r"<item>.*?<title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>", x, re.DOTALL
    ):
        et = (
            parsedate_to_datetime(pd_)
            .astimezone(ZoneInfo("America/New_York"))
            .replace(tzinfo=None)
        )
        if lo <= et <= hi and (best is None or et < best[0]):
            best = (et, html.unescape(t))
    if not best:
        return "", "", ""
    src = best[1].rsplit(" - ", 1)[-1]
    # Google News gives old items a placeholder time on the hour (07:00 GMT); treat those as day-only.
    if best[0].minute == 0 and best[0].second == 0:
        return best[0].strftime("%Y-%m-%d"), src, "day"
    return best[0].strftime("%Y-%m-%d %H:%M"), src, "minute"


def in_market(ts: str, prec: str) -> str:
    if not ts:
        return "unknown"
    d, hm = ts.split() if " " in ts else (ts, "")
    if d not in set(cal()):
        return "no"
    if prec not in ("minute", PRICE_PREC):
        # an upper-bound time before the open still proves it was out before the open
        return "no" if hm and hm < "09:30" else "unknown"
    return "yes" if "09:30" <= hm < "16:00" else "no"


# ---------- Polygon minute bars ----------
POLY_START = "2024-10-15"
PRICE_PREC = "inferred from price"
# Unscheduled outcomes with big moves whose ruling time no free source gives: the first
# price jump in 1-minute bars stands in for it (an upper bound on when it was public).
# Docket entries for the same 5 cases from CourtListener searches made on 2026-10-14
# (cached in raw/cl/). The time is meta.date_created converted to ET: when CourtListener
# first recorded the entry, so the court posted it at or before then.
# case_id: (time ET, document URL, docket URL, what the entry is)
CL_SEEN = {
    "mc_2024_tpr_cpri": (
        "2024-10-24 16:08",
        "https://www.courtlistener.com/docket/68465585/339/federal-trade-commission-v-tapestry-inc/",
        "https://www.courtlistener.com/docket/68465585/federal-trade-commission-v-tapestry-inc/",
        "opinion and order granting the preliminary injunction (doc 339)",
    ),
    "mc_2025_srdx_gtcr": (
        "2025-11-11 11:15",
        "https://www.courtlistener.com/docket/69712670/445/federal-trade-commission-v-gtcr-bc-holdings-llc/",
        "https://www.courtlistener.com/docket/69712670/federal-trade-commission-v-gtcr-bc-holdings-llc/",
        "minute entry for the ruling the judge gave by phone on 2025-11-10 (doc 445)",
    ),
    "mc_2025_ew_jena": (
        "2026-01-09 16:24",
        "https://www.courtlistener.com/docket/71040538/173/federal-trade-commission-v-edwards-lifesciences-corporation/",
        "https://www.courtlistener.com/docket/71040538/federal-trade-commission-v-edwards-lifesciences-corporation/",
        "sealed memorandum opinion granting the preliminary injunction (doc 173)",
    ),
    "mc_2024_kr_aci_ftc": (
        "2024-12-10 17:09",
        "https://www.courtlistener.com/docket/68284514/524/federal-trade-commission-v-kroger-company/",
        "https://www.courtlistener.com/docket/68284514/federal-trade-commission-v-kroger-company/",
        "opinion and order granting the preliminary injunction (doc 524)",
    ),
    "mc_2026_nxst_tgna": (
        "2026-04-17 20:43",
        "https://www.courtlistener.com/docket/72515406/172/in-re-nexstar-tegna-merger-litigation/",
        "https://www.courtlistener.com/docket/72515406/in-re-nexstar-tegna-merger-litigation/",
        "order granting a preliminary injunction (doc 172)",
    ),
}
PRICE_TIMED = {
    "mc_2024_tpr_cpri",
    "mc_2025_srdx_gtcr",
    "mc_2025_ew_jena",
    "mc_2024_kr_aci_ftc",
    "mc_2026_nxst_tgna",
}


def _poly_minutes(sym: str, d: str) -> list[tuple[str, float]]:
    """All 1-minute closes on day d (04:00-20:00 ET) as ('YYYY-MM-DD HH:MM', close)."""
    import os

    key = os.environ.get("POLYGON_API_KEY", "")
    u = f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/{d}/{d}?adjusted=true&sort=asc&limit=50000"
    path = _key("polygon", u)
    if path.exists():
        t = path.read_text()
    else:
        t = ""
        for _ in range(3):  # the key is shared with other sessions; back off on 429
            time.sleep(13)
            try:
                r = requests.get(u + "&apiKey=" + key, timeout=60)
            except requests.RequestException:
                continue
            if r.status_code == 200:
                t = r.text
                path.write_text(t)
                break
            if r.status_code != 429:
                break
            time.sleep(60)
    try:
        res = json.loads(t).get("results", []) if t else []
    except ValueError:
        return []
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/New_York")
    return [
        (datetime.fromtimestamp(b["t"] / 1000, tz).strftime("%Y-%m-%d %H:%M"), b["c"])
        for b in res
    ]


def _mins(t0: str, t1: str) -> int:
    return int(
        (datetime.fromisoformat(t1) - datetime.fromisoformat(t0)).total_seconds() // 60
    )


def price_jump(sym: str, dd: str) -> str:
    """First 1-minute bar, from 04:00 ET on the decision day to the next day's close, that moves
    in the direction of the two-day move by at least 2% and 30% of that move, and holds for
    3 bars. The first bar of the decision day is not compared with the prior close. '' if none."""
    d1 = eff_day(dd)
    d2, d0 = shift(d1, 1), shift(d1, -1)
    p = px(sym)
    if d1 < POLY_START or d0 not in p or d2 not in p:
        return ""
    p0, pe = p[d0][0], p[d2][0]
    move = pe / p0 - 1
    if abs(move) < 0.03:
        return ""
    bars = [b for d in (d1, d2) for b in _poly_minutes(sym, d) if b[0] < f"{d2} 16:00"]
    for i in range(1, len(bars)):
        r = bars[i][1] / bars[i - 1][1] - 1
        mid = (bars[i][1] + bars[i - 1][1]) / 2
        nxt = [c for _, c in bars[i + 1 : i + 4]]
        # the jump has to hold for the next 3 bars, which drops lone pre-market prints
        held = len(nxt) == 3 and all((c - mid) * move > 0 for c in nxt)
        if r * move > 0 and abs(r) >= max(0.02, 0.3 * abs(move)) and held:
            return bars[i][0]
    return ""


def half_after(sym: str, ts: str, dd: str) -> tuple[str, int | None]:
    """(minute_data_available, minutes from ts until the stock had made half of its move
    to the close of the session that priced the news)."""
    d1 = eff_day(dd)
    if d1 < POLY_START or not _poly_minutes(sym, d1):
        return "no", None
    if not ts:
        return "yes", None
    day = eff_day(ts[:10], ts[11:])
    p = px(sym)
    if day not in p:
        return "yes", None
    pe = p[day][1]  # raw close, to match Polygon's split-only adjusted bars
    bars = [
        b
        for d in sorted({ts[:10], day})
        for b in _poly_minutes(sym, d)
        if b[0] < f"{day} 16:00"
    ]
    before = [c for t, c in bars if t < ts]
    pb = before[-1] if before else p.get(shift(day, -1), (None, None))[1]
    if pb is None:
        return "yes", None
    target = pb + (pe - pb) / 2
    for t, c in bars:
        if t >= ts and (c - target) * (pe - pb) >= 0:
            # a half-move first reached in a later session is not a fast reaction
            return ("yes", _mins(ts, t)) if t[:10] == ts[:10] else ("yes", None)
    return "yes", None


COLS = [
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


def window(sym: str, bench: str, d: str, hhmm: str) -> tuple:
    """(ret, abnormal ret, end day, note) for an event on date d at hhmm ET ('' = unknown -> 2-day)."""
    if not px(sym):
        return None, None, None, f"no Yahoo prices for {sym}"
    e = eff_day(d, hhmm)
    end = e if hhmm else shift(e, 1)
    r, b = ret(sym, e, end), ret(bench, e, end)
    note = "" if hhmm else f"time unknown, 2-day return {e} to {end}"
    return r, (round(r - b, 4) if r is not None and b is not None else None), end, note


def build() -> None:
    rows = []
    for c in CASES:
        fd, dd = c["filed"], c["decision"]
        # timing of the decisive event, case-wide: earliest of the news and every party's 8-K
        news_ts, news_src, news_prec = news_first(c["q"], dd)
        d0 = (date.fromisoformat(dd) - timedelta(days=1)).isoformat()
        d3 = (date.fromisoformat(dd) + timedelta(days=3)).isoformat()
        rels, earn = {}, {}
        for p in c["parties"]:
            cik = cik_of(p["ticker"])
            k8 = eight_ks(cik, d0, d3) if cik else []
            kw = c.get("kw") or p["cp"].split(" (")[0]
            hits = [k for k in k8 if k["et"][:10] >= dd and mentions(k["url"], kw)]
            rels[p["ticker"]] = hits[0]["et"] if hits else ""
            earn[p["ticker"]] = any("2.02" in k["items"] for k in k8)
        case_notes = []
        first_ts, first_src, prec = "", "", ""
        if news_ts:
            first_ts, first_src, prec = news_ts, f"news report ({news_src})", news_prec
        filed = sorted((v, k) for k, v in rels.items() if v)
        if filed:
            rel, tk = filed[0]
            if (
                not first_ts
                or rel[:10] < first_ts[:10]
                or (prec == "day" and rel[:10] == first_ts[:10])
                or (prec == "minute" and rel < first_ts)
            ):
                same_day = prec == "day" and first_ts and rel[:10] == first_ts[:10]
                if same_day:
                    case_notes.append(
                        f"a news report ({news_src}) appeared the same day without a time, so the 8-K time "
                        "is only the latest the news could have been public (time_precision=day)"
                    )
                first_ts, first_src = rel, f"{tk} 8-K (SEC EDGAR acceptance time)"
                prec = "day" if same_day else "minute"
        if c.get("first"):
            first_ts, first_src, prec = c["first"]
        elif c["id"] in PRICE_TIMED:
            jumps = sorted(
                (j, p["ticker"])
                for p in c["parties"]
                if (j := price_jump(p["ticker"], dd))
            )
            cl = CL_SEEN.get(c["id"])
            if cl:
                case_notes.append(
                    f"CourtListener first recorded the {cl[3]} at {cl[0]} ET ({cl[1]}); "
                    "the court posted it at or before then"
                )
            if not jumps:
                case_notes.append(
                    "no clear price jump in Polygon 1-minute bars (move under 3% or spread out)"
                )
            if jumps and (not cl or jumps[0][0] <= cl[0]):
                case_notes.append(
                    f"first_public_time_et is the first price jump in {jumps[0][1]}'s Polygon 1-minute bars "
                    f"(earlier best source: {first_src} {first_ts}); the outcome was public no later "
                    "than this, possibly a few minutes earlier"
                )
                first_ts, prec = jumps[0][0], PRICE_PREC
                first_src = f"first price jump, Polygon 1-minute bars ({jumps[0][1]})"
            elif cl:
                first_ts, prec = cl[0], "minute"
                first_src = "court docket via CourtListener RECAP (time CourtListener recorded it)"
        dtime = c.get("dtime") or (
            first_ts.split()[1] if prec == "minute" and first_ts.startswith(dd) else ""
        )
        for p in c["parties"]:
            t, notes = p["ticker"], list(case_notes)
            fdt = c.get("filed_time", "")
            cik = cik_of(t)
            rel = rels[t]
            if earn[t]:
                notes.append(
                    "CAUTION: the company released earnings (8-K Item 2.02) around the decision; "
                    "the decision-day move mixes both"
                )
            r_f, a_f, _, n_f = window(t, p["bench"], fd, fdt)
            r_d, a_d, end_d, n_d = window(t, p["bench"], dd, dtime)
            if px(t) and PX_SOURCE.get(t) != "Yahoo":
                notes.append(f"prices from {PX_SOURCE[t]}")
            if n_f:
                notes.append("filing day: " + n_f)
            if n_d:
                notes.append("decision day: " + n_d)
            r5 = None
            if end_d:
                e = eff_day(dd, dtime)
                r5 = ret(t, e, shift(e, 5))
            adv = None
            if px(t) and end_d:
                days = cal()
                i = days.index(eff_day(dd, dtime))
                vals = [px(t)[x][2] for x in days[max(0, i - 20) : i] if x in px(t)]
                adv = round(sum(vals) / len(vals)) if vals else None
            # facts known at filing
            mcap = rev = None
            if cik:
                facts = sec_json(
                    f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
                )
                sh = shares_out(facts, fd)
                pr = px(t).get(shift(eff_day(fd), -1)) if px(t) else None
                if sh and pr:
                    mcap = round(sh * pr[1])
                rev = ttm_revenue(facts, fd)
            else:
                notes.append("no SEC CIK found")
            if t == "SNY":
                mcap, rev = None, None
                notes.append(
                    "Sanofi files in EUR under IFRS; market cap and revenue left blank"
                )
            stake = p["deal"] if p["role"] == "acquirer" else None
            if p["role"] == "target":
                pre = px(t).get(shift(eff_day(fd), -1)) if px(t) else None
                notes.append(
                    f"deal value ${p['deal'] / 1e9:.3g}B"
                    if p["deal"]
                    else "deal value not disclosed"
                )
                if p["price"]:
                    notes.append(f"deal price ${p['price']:.2f}")
                else:
                    notes.append("deal price: no per-share cash price")
                if pre:
                    notes.append(f"close day before complaint ${pre[1]:.2f}")
            if p["note"]:
                notes.append(p["note"])
            notes.append(c["events"])
            timed = prec in ("minute", PRICE_PREC)
            avail, mins = half_after(t, first_ts if timed else "", dd)
            lead = _mins(first_ts, rel) if rel and timed else None
            rows.append(
                {
                    "case_id": c["id"],
                    "case_type": "merger_challenge",
                    "case_name": c["name"],
                    "court": c["court"],
                    "docket_number": c.get("docket", ""),
                    "docket_url": CL_SEEN[c["id"]][2]
                    if c["id"] in CL_SEEN
                    else c.get("docket_url") or c.get("src", ""),
                    "ticker": t,
                    "company": p["company"],
                    "company_role": p["role"],
                    "counterparty": p["cp"],
                    "counterparty_ticker": p["cpt"],
                    "filed_date": fd,
                    "trial_start_date": c.get("trial", ("", ""))[0],
                    "trial_end_date": c.get("trial", ("", ""))[1],
                    "decision_date": dd,
                    "decision_time_et": dtime,
                    "decision_known_in_advance": c["known"],
                    "decision_source_url": c["dsrc"],
                    "outcome": c["outcome"],
                    "outcome_for_company": p["ofc"],
                    "days_filed_to_decision": (
                        date.fromisoformat(dd) - date.fromisoformat(fd)
                    ).days,
                    "market_cap_usd_at_filing": mcap,
                    "revenue_ttm_usd_at_filing": rev,
                    "revenue_at_stake_usd": stake,
                    "revenue_at_stake_share": round(stake / rev, 4)
                    if stake and rev
                    else None,
                    "ret_filing_day": r_f,
                    "abn_ret_filing_day": a_f,
                    "ret_decision_day": r_d,
                    "abn_ret_decision_day": a_d,
                    "ret_decision_plus5": r5,
                    "adv_usd_20d_before_decision": adv,
                    "implied_move_before_decision": None,
                    "settlement_amount_usd": None,
                    "confidence": c["conf"],
                    "sources": c["src"] + " ; " + c["dsrc"],
                    "notes": "; ".join(n for n in notes if n),
                    "first_public_source": first_src,
                    "first_public_time_et": first_ts,
                    "time_precision": prec,
                    "during_market_hours": in_market(first_ts, prec),
                    "company_release_time_et": rel,
                    "lead_minutes_vs_company_release": lead,
                    "minutes_to_half_move": mins,
                    "minute_data_available": avail,
                }
            )
            print(c["id"], t, r_d, a_d, first_ts, rel, mins, flush=True)
    with open(OUT / "cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print("rows:", len(rows), "cases:", len(CASES))


def stats() -> None:
    """Numbers quoted in docs/universe_merger_challenge.md."""
    import statistics as st

    with open(OUT / "cases.csv") as fh:
        rows = list(csv.DictReader(fh))
    cases = {r["case_id"]: r for r in rows}
    print(
        "rows",
        len(rows),
        "cases",
        len(cases),
        "tickers",
        len({r["ticker"] for r in rows}),
    )
    by_year: dict[str, int] = {}
    for r in cases.values():
        by_year[r["filed_date"][:4]] = by_year.get(r["filed_date"][:4], 0) + 1
    print("filed per year", dict(sorted(by_year.items())))
    out: dict[str, int] = {}
    for r in cases.values():
        out[r["outcome"]] = out.get(r["outcome"], 0) + 1
    print("outcomes (cases)", out)
    ofc: dict[str, int] = {}
    for r in rows:
        ofc[r["outcome_for_company"]] = ofc.get(r["outcome_for_company"], 0) + 1
    print("outcome_for_company (rows)", ofc)
    a = [
        (abs(float(r["abn_ret_decision_day"])), r)
        for r in rows
        if r["abn_ret_decision_day"]
    ]
    print("rows with decision-day abnormal return", len(a), "of", len(rows))
    for k in (0.05, 0.10, 0.25):
        print(f"  abs > {k:.0%}:", sum(x > k for x, _ in a))
    print("  median abs", round(st.median(x for x, _ in a), 4))
    for x, r in sorted(a, key=lambda t: -t[0])[:10]:
        print(
            "  ",
            r["ticker"],
            r["case_id"],
            r["decision_date"],
            r["abn_ret_decision_day"],
            r["company_role"],
        )
    acq = [x for x, r in a if r["company_role"] == "acquirer"]
    tgt = [x for x, r in a if r["company_role"] == "target"]
    print(
        "median abs acquirer",
        round(st.median(acq), 4),
        len(acq),
        "target",
        round(st.median(tgt), 4) if tgt else "",
        len(tgt),
    )
    f = [abs(float(r["abn_ret_filing_day"])) for r in rows if r["abn_ret_filing_day"]]
    print(
        "filing day: n",
        len(f),
        "median abs",
        round(st.median(f), 4),
        ">5%",
        sum(x > 0.05 for x in f),
    )
    fast = [
        r
        for r in rows
        if r["during_market_hours"] == "yes" and r["decision_known_in_advance"] == "no"
    ]
    print("market-hours, no preset date:", len(fast))
    for r in fast:
        print(
            "  ",
            r["ticker"],
            r["first_public_time_et"],
            r["first_public_source"],
            r["lead_minutes_vs_company_release"],
            r["minutes_to_half_move"],
            r["abn_ret_decision_day"],
        )
    print(
        "precision",
        {
            k: sum(r["time_precision"] == k for r in rows)
            for k in ("minute", PRICE_PREC, "day", "")
        },
    )
    print(
        "market hours",
        {
            k: sum(r["during_market_hours"] == k for r in rows)
            for k in ("yes", "no", "unknown")
        },
    )
    leads = [
        int(r["lead_minutes_vs_company_release"])
        for r in rows
        if r["lead_minutes_vs_company_release"]
    ]
    print("leads", leads)
    print(
        "minute data",
        sum(r["minute_data_available"] == "yes" for r in rows),
        "half-move",
        [r["minutes_to_half_move"] for r in rows if r["minutes_to_half_move"]],
    )
    print(
        "conf",
        {k: sum(r["confidence"] == k for r in rows) for k in ("high", "medium", "low")},
    )
    print("no prices", [r["ticker"] for r in rows if not r["ret_decision_day"]])


if __name__ == "__main__":
    {"sources": sources, "build": build, "stats": stats}[sys.argv[1]]()
