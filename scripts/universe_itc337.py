"""Every Section 337 (ITC import-ban) investigation instituted or decided since
2021-01-01, the US-listed parties in each, and the stock moves on key dates.

Stages (run in order; every download is cached under data/universe/itc337/raw/):
  fr      list every International Trade Commission Federal Register notice and
          download the full text of those that name a 337-TA investigation
  parse   build one record per investigation (parties, dates, outcome)
  ...

Only public, free sources: federalregister.gov API, sec.gov, Yahoo chart API,
Polygon.io (POLYGON_API_KEY). Keys are read from the environment, never printed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import UTC, date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "itc337"
RAW = OUT / "raw"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
YAHOO_UA = "Mozilla/5.0"
WEB_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)
START = date(2021, 1, 1)
FR_FROM = date(2018, 1, 1)  # older notices give parties for cases decided after 2021

_last: dict[str, float] = {}
_GAP = {
    "sec.gov": 0.15,
    "federalregister.gov": 0.25,
    "yahoo.com": 0.5,
    "polygon.io": 12.5,
    "courtlistener.com": 13.0,
}


def _throttle(host: str) -> None:
    for key, gap in _GAP.items():
        if host.endswith(key):
            wait = _last.get(key, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[key] = time.time()


def cache_path(url: str, sub: str) -> Path:
    clean = re.sub(r"(apiKey|token)=[^&]+", "", url)
    digest = hashlib.sha1(clean.encode()).hexdigest()[:12]
    name = re.sub(r"[^A-Za-z0-9]+", "_", clean)[-120:] + "_" + digest + ".txt"
    return RAW / sub / name


def get(url: str, sub: str = "misc", tries: int = 4, refresh: bool = False) -> str:
    """GET with an on-disk cache; '' on failure. Secrets are stripped from the key."""
    key = cache_path(url, sub)
    if key.exists() and not refresh:
        return key.read_text()
    key.parent.mkdir(parents=True, exist_ok=True)
    host = urllib.parse.urlparse(url).hostname or ""
    ua = SEC_UA if host.endswith("sec.gov") else WEB_UA
    if host.endswith("finance.yahoo.com"):
        ua = YAHOO_UA  # Yahoo 429s a full Chrome UA but serves a plain one
    headers = {"User-Agent": ua}
    if host.endswith("courtlistener.com") and os.environ.get("COURTLISTENER_API_TOKEN"):
        headers["Authorization"] = "Token " + os.environ["COURTLISTENER_API_TOKEN"]
    for i in range(tries):
        _throttle(host)
        try:
            r = requests.get(url, headers=headers, timeout=60)
        except requests.RequestException:
            time.sleep(3 * (i + 1))
            continue
        if r.status_code == 200:
            key.write_text(r.text)
            return r.text
        if r.status_code in (202, 429, 500, 502, 503, 504):
            time.sleep(15 * (i + 1))
            continue
        return ""
    return ""


# ---------------------------------------------------------------- stage: fr
FR_API = "https://www.federalregister.gov/api/v1/documents.json"
FR_FIELDS = [
    "title",
    "docket_ids",
    "publication_date",
    "document_number",
    "raw_text_url",
    "html_url",
    "action",
    "type",
]


def fr_month(y: int, m: int) -> list[dict]:
    end = date(y + (m == 12), m % 12 + 1, 1)
    last = date.fromordinal(end.toordinal() - 1)
    params = [
        ("conditions[agencies][]", "international-trade-commission"),
        ("conditions[publication_date][gte]", f"{y}-{m:02d}-01"),
        ("conditions[publication_date][lte]", last.isoformat()),
        ("per_page", "1000"),
        ("order", "oldest"),
    ] + [("fields[]", f) for f in FR_FIELDS]
    url = FR_API + "?" + urllib.parse.urlencode(params)
    # the current month is still filling up; refresh it every run
    t = get(url, "fr_index", refresh=end > date.today())
    d = json.loads(t) if t else {}
    if d.get("count", 0) > 1000:
        raise SystemExit(f"more than 1000 ITC notices in {y}-{m}")
    return d.get("results", [])


def stage_fr() -> list[dict]:
    docs = []
    y, m = FR_FROM.year, FR_FROM.month
    today = date.today()
    while (y, m) <= (today.year, today.month):
        for r in fr_month(y, m):
            ids = " ".join(r.get("docket_ids") or [])
            if "337" in ids or "337-TA" in (r.get("title") or ""):
                docs.append(r)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    print(f"{len(docs)} Section 337 notices since {FR_FROM}", file=sys.stderr)
    for i, r in enumerate(docs):
        r["text"] = get(r["raw_text_url"], "fr_text")
        if i % 200 == 0:
            print(i, file=sys.stderr)
    (OUT / "raw" / "fr_docs.json").write_text(json.dumps(docs))
    return docs


# ---------------------------------------------------------------- IDS universe
IDS_URL = "https://ids.usitc.gov/investigations.json"
IDS_FILE = RAW / "ids_investigations.json"
CASE_URL = "https://ids.usitc.gov/case/{}"
COURT = "US International Trade Commission"


def stage_ids() -> None:
    """USITC's public Investigations Database System bulk file (data.gov)."""
    if IDS_FILE.exists():
        return
    r = requests.get(IDS_URL, headers={"User-Agent": WEB_UA}, timeout=300)
    r.raise_for_status()
    IDS_FILE.write_bytes(r.content)


def mdy(v) -> date | None:
    if isinstance(v, dict):
        v = v.get("date")
    if not v:
        return None
    if "T" in v or re.match(r"\d{4}-", v):
        d = date.fromisoformat(v[:10])
        return d if d.year >= 1975 else None
    m, d, y = v.split("-")
    if int(y) < 1975:  # a few typos in IDS, e.g. year 0221
        return None
    return date(int(y), int(m), int(d))


def name_of(x) -> str | None:
    if not x:
        return None
    return x.get("Name") or x.get("name") or x.get("finalDeterminationType")


# Hand-built map from IDS party names to US exchange tickers. First match wins;
# a blank ticker means "checked, not US exchange-listed". "A:date:B" means ticker
# A before that date and B from it ("-" = not listed). Built by reading every
# respondent/complainant name in the window against SEC's ticker file and
# known parents; anything not here is treated as private or foreign-only.
ALIASES = r"""
pattern,ticker,parent,note
^ADT (LLC|Security)|^The ADT Security,ADT,ADT Inc.,
^AbbVie,ABBV,AbbVie Inc.,
^Adeia,ADEA,Adeia Inc.,
^Advance Auto Parts,AAP,Advance Auto Parts,
^Advanced Micro Devices|^ATI Technologies,AMD,Advanced Micro Devices,
^Alarm\.com,ALRM,Alarm.com Holdings,
^Align Technology,ALGN,Align Technology,
^Alphabet|^Google|^Fitbit,GOOGL,Alphabet Inc.,Fitbit owned by Google since Jan 2021
^NJOY,-:2023-06-01:MO,NJOY / Altria,private before Altria bought it
^Altria,MO,Altria Group,NJOY owned by Altria from June 2023
^Alvotech,ALVO,Alvotech,Nasdaq listing from June 2022
^Amazon,AMZN,Amazon.com,
^Amphenol,APH,Amphenol,
^Amtech Systems,-,Amtech Systems LLC,private Texas RFID maker; not Amtech Systems Inc (ASYS)
^Analog Devices,ADI,Analog Devices,
^Apple Inc,AAPL,Apple,
^ArcelorMittal,MT,ArcelorMittal,
^Archer Aviation,ACHR,Archer Aviation,
^Arista Networks,ANET,Arista Networks,
^Arlo Technologies,ARLO,Arlo Technologies,
^Arris|^CommScope|^Ruckus,COMM:2026-01-13:VISN,CommScope (renamed Vistance Networks Jan 2026),
^Arrow Electronics,ARW,Arrow Electronics,
^Ascendis,ASND,Ascendis Pharma,
^AutoZone,AZO,AutoZone,
^Avigilon,MSI,Motorola Solutions,Avigilon owned by Motorola Solutions
^Avnet,AVT,Avnet,
^Benchmark Electronics,BHE,Benchmark Electronics,
^Best Buy,BBY,Best Buy,
^BioMarin,BMRN,BioMarin,
^Biofrontera,BFRI,Biofrontera Inc.,
^Bioverativ|^Genzyme,SNY,Sanofi,Sanofi subsidiaries
^Brita LP,CLX,Clorox,Brita LP is a Clorox subsidiary
^Broadcom,AVGO,Broadcom,
^CCC INTELLIGENT,CCC,CCC Intelligent Solutions,
^CVS,CVS,CVS Health,
^Cabot Microelectronics|^CMC Materials,CCMP:2022-07-06:ENTG,CMC Materials,acquired by Entegris July 2022
^Cadence Design,CDNS,Cadence Design Systems,
^Caesarstone,CSTE,Caesarstone,
^Canadian Solar,CSIQ,Canadian Solar,
^Cardinal Health,CAH,Cardinal Health,
^Carrier Global,CARR,Carrier Global,
^Castle Biosciences,CSTL,Castle Biosciences,
^Caterpillar,CAT,Caterpillar,
^Celanese,CE,Celanese,
^Celestica,CLS,Celestica,
^Cercacor|^Masimo,MASI,Masimo,Cercacor is Masimo's affiliate
^Cerence,CRNC,Cerence,
^Ceribell,CBLL,Ceribell,IPO Oct 2024
^Charter Communications|^Spectrum Management Holding,CHTR,Charter Communications,
^Cisco,CSCO,Cisco,
^Comcast,CMCSA,Comcast,
^Corning,GLW,Corning,
^Credo,CRDO,Credo Technology,IPO Jan 2022
^Cricut,CRCT,Cricut,
^Crocs\b,CROX,Crocs,
^Cytek,CTKB,Cytek Biosciences,
^DISH|^Sling TV,DISH:2024-01-02:SATS,DISH Network / EchoStar,
^Ouster,OUST,Ouster,
^EchoStar,SATS,EchoStar,DISH merged into EchoStar Dec 2023; before that DISH traded as DISH
^Dell,DELL,Dell Technologies,
^Dolby,DLB,Dolby Laboratories,
^Dragonfly Energy,DFLI,Dragonfly Energy,
^DuPont,DD,DuPont de Nemours,
^Eaton,ETN,Eaton,
^Ecobee,-:2021-12-01:GNRC,Generac,Ecobee owned by Generac from Dec 2021
^Eli Lilly,LLY,Eli Lilly,
^Emerson Electric,EMR,Emerson Electric,
^Ericsson|^Telefonaktiebolaget LM Ericsson,ERIC,Ericsson,
^Ethicon,JNJ,Johnson & Johnson,
^Everspin,MRAM,Everspin,
^First Solar,FSLR,First Solar,
^Flex Ltd,FLEX,Flex,
^Fujifilm|^FUJIFILM,,,Fujifilm not exchange-listed in US
^GM Global|^General Motors,GM,General Motors,
^General Electric,GE,General Electric,
^Genmab,GMAB,Genmab,
^Genuine Parts|^National Automotive Parts Association,GPC,Genuine Parts,NAPA
^GlobalFoundries,GFS,GlobalFoundries,IPO Oct 2021
^GoPro,GPRO,GoPro,
^Graco Children|^Newell Brands,NWL,Newell Brands,
^Garmin,GRMN,Garmin,
^Granite Construction,GVA,Granite Construction,
^HP Inc|^HP. Inc,HPQ,HP Inc.,
^Hand Held Products|^Metrologic|^Honeywell,HON,Honeywell,
^Hasbro,HAS,Hasbro,
^Helen of Troy|^Steel Technology. LLC d/b/a Hydro Flask,HELE,Helen of Troy,
^Hesai,HSAI,Hesai Group,IPO Feb 2023
^Hewlett Packard Enterprise,HPE,Hewlett Packard Enterprise,
^Hologic,HOLX,Hologic,
^Home Depot|^The Home Depot,HD,Home Depot,
^Hubbell,HUBB,Hubbell,
^HydraFacial,SKIN,Beauty Health,
^ICON Health|^ICON Fitness|^iFIT,,,iFIT is private
^ImmunoGen,IMGN:2024-02-12:ABBV,ImmunoGen,acquired by AbbVie Feb 2024
^InMode|^Invasix,INMD,InMode,
^Infineon,,,Infineon trades OTC only
^Ingram Micro,-:2024-10-24:INGM,Ingram Micro,private until IPO 2024-10-24
^Innovative Eyewear,LUCY,Innovative Eyewear,
^Intel Corp,INTC,Intel,
^InterDigital,IDCC,InterDigital,
^Intuitive Surgical,ISRG,Intuitive Surgical,
^Itron,ITRI,Itron,
^Illinois Tool Works,ITW,Illinois Tool Works,
^Johnson Controls,JCI,Johnson Controls,
^JinkoSolar,JKS,JinkoSolar,
^Joby,JOBY,Joby Aviation,
^Juniper Networks,JNPR:2025-07-02:HPE,Juniper Networks,acquired by HPE July 2025
^Keysight,KEYS,Keysight,
^Knowles,KN,Knowles,
^Kyocera,,,Kyocera delisted its US ADR in 2001
^L&P Property|^Leggett & Platt,LEG,Leggett & Platt,
^LG Display,LPL,LG Display,
^LKQ,LKQ,LKQ,
^Lifetime Brands,LCUT,Lifetime Brands,
^Logitech,LOGI,Logitech,
^Lowe,LOW,Lowe's,
^lululemon,LULU,Lululemon,
^M-I LLC,SLB,SLB (Schlumberger),M-I SWACO is an SLB company
^MACOM,MTSI,MACOM,
^Marvell,MRVL,Marvell,
^MaxLinear,MXL,MaxLinear,
^Medtronic,MDT,Medtronic,
^Meta Platforms,META,Meta Platforms,
^Micron,MU,Micron,
^Microsoft,MSFT,Microsoft,
^Mohawk,MHK,Mohawk Industries,
^Monolithic Power,MPWR,Monolithic Power,
^Monster Energy,MNST,Monster Beverage,
^Motorola Solutions,MSI,Motorola Solutions,
^NVIDIA,NVDA,NVIDIA,
^NXP,NXPI,NXP Semiconductors,
^NetApp,NTAP,NetApp,
^Netgear,NTGR,Netgear,
^Nike,NKE,Nike,
^Nokia,NOK,Nokia,
^Novartis,NVS,Novartis,
^O.Reilly Automotive,ORLY,O'Reilly Automotive,
^Velodyne,VLDR:2023-02-10:OUST,Velodyne Lidar / Ouster,Velodyne (VLDR) merged into Ouster Feb 2023
^Palo Alto Networks,PANW,Palo Alto Networks,
^Parker Hannifin,PH,Parker Hannifin,
^Peloton,PTON,Peloton,
^Perrigo,PRGO,Perrigo,
^Philip Morris,PM,Philip Morris International,
^Philips|^Koninklijke Philips,PHG,Koninklijke Philips,
^Polaris,PII,Polaris,
^Purple Innovation,PRPL,Purple Innovation,
^QVC,QRTEA:2025-02-24:QVCGA,Qurate Retail / QVC Group,
^Qualcomm,QCOM,Qualcomm,
^R\.J\. Reynolds|^RAI |^Reynolds Marketing Services,BTI,British American Tobacco,Reynolds American owned by BAT
^Regeneron,REGN,Regeneron,
^Resideo,REZI,Resideo,
^Roku,ROKU,Roku,
^Root Technology,,,Root Technology Ltd is not Root Inc (insurer)
^STMicroelectronics,STM,STMicroelectronics,
^Samsara,IOT,Samsara,
^SharkNinja,SN,SharkNinja,NYSE listing from July 2023
^Shoals,SHLS,Shoals Technologies,
^Seer. Inc,SEER,Seer,
^Silicon Laboratories,SLAB,Silicon Labs,
^Skechers,SKX:2025-09-12:-,Skechers,taken private Sept 2025
^Skyworks,SWKS,Skyworks,
^SolarEdge,SEDG,SolarEdge,
^Sonos,SONO,Sonos,
^Sony,SONY,Sony Group,
^Stanley Black|^Black & Decker,SWK,Stanley Black & Decker,
^Stryker,SYK,Stryker,
^SunCoke|^Jewell Coke,SXC,SunCoke Energy,
^Super Micro Computer,SMCI,Super Micro Computer,
^Symbol Technologies|^Zebra Technologies,ZBRA,Zebra Technologies,
^T-Mobile,TMUS,T-Mobile US,
^T1 Energy|^T1 G1 Dallas,TE,T1 Energy,formerly FREYR; owns the Trina Dallas plant from Dec 2024
^TE Connectivity,TEL,TE Connectivity,
^TSMC|^Taiwan Semiconductor Manufacturing,TSM,TSMC,
^Tesla,TSLA,Tesla,
^Teva,TEVA,Teva,
^Tower Semiconductor|^Tower US Holdings|^Tower Partners Semiconductor|^Tower NPB,TSEM,Tower Semiconductor,
^Toyo Co|^Toyo Solar,TOYO,TOYO Co.,listed July 2024
^Traeger,COOK,Traeger,
^Ubiquiti,UI,Ubiquiti,
^Ulta,ULTA,Ulta Beauty,
^Unilever,UL,Unilever,
^Universal Electronics,UEIC,Universal Electronics,
^US Synthetic,DOV,Dover,US Synthetic is a Dover company
^VIZIO|^Vizio,VZIO:2024-12-03:WMT,VIZIO Holding,acquired by Walmart Dec 2024
^Vicor,VICR,Vicor,
^Viking Therapeutics,VKTX,Viking Therapeutics,
^VinFast,VFS,VinFast Auto,listed Aug 2023
^Visteon,VC,Visteon,
^Vivint,VVNT:2023-03-10:NRG,Vivint Smart Home,acquired by NRG March 2023
^Vuzix,VUZI,Vuzix,
^Walmart,WMT,Walmart,
^Wesco,,,CHECK: Wesco Company may not be WESCO International
^West Pharma,WST,West Pharmaceutical Services,
^Western Digital,WDC,Western Digital,
^Whirlpool,WHR,Whirlpool,
^Xylem,XYL,Xylem,
^Zepp,ZEPP,Zepp Health,
^Zimmer MedizinSysteme,,,not Zimmer Biomet
^Zimmer,ZBH,Zimmer Biomet,
^iRobot,IRBT,iRobot,
^Panasonic,,,Panasonic not US-listed
^Nintendo,,,Nintendo trades OTC only
^Lenovo|^Motorola Mobility|^Motorola \(Wuhan\)|^Motorola Mobile,,,Lenovo not US-listed
^Samsung|^LG Electronics|^LG Energy|^LG Chem|^SK |^Hyundai|^Kia ,,,Korean parents not US-listed (except LG Display)
^Siemens,,,Siemens trades OTC only
^Denso,,,not US-listed
^Electrolux,,,not US-listed
^MediaTek|^Realtek,,,not US-listed
^Canon,,,Canon ADR left NYSE in 2023? not used; Canon treated as not US-listed
"""


def load_aliases() -> list[tuple[re.Pattern, str, str, str]]:
    import csv
    import io

    out = []
    for r in csv.DictReader(io.StringIO(ALIASES.strip())):
        out.append(
            (
                re.compile(r["pattern"], re.IGNORECASE),
                r["ticker"],
                r["parent"],
                r["note"],
            )
        )
    return out


def match_ticker(name: str, aliases) -> tuple[str, str, str] | None:
    for rx, tic, parent, note in aliases:
        if rx.search(name.strip()):
            return (tic, parent, note) if tic else None
    return None


def in_window(c: dict) -> bool:
    ds = [
        c[k]
        for k in ("complaint", "instituted", "id_date", "fd_date", "terminated")
        if c[k]
    ]
    # IDS still flags some 1990s-2000s cases "Active" with no dates; skip those
    return any(d >= START for d in ds) or (c["status"] not in TERMINAL and bool(ds))


TERMINAL = {"Terminated", "Complaint/Request Withdrawn", "Not Instituted", "Inactive"}


def stage_parse() -> list[dict]:
    """One record per Section 337 violation investigation in the window."""
    data = json.loads(IDS_FILE.read_text())["data"]
    aliases = load_aliases()
    cases = []
    for x in data:
        num = str(x.get("Investigation Number") or "")
        if (
            not num.startswith("337-")
            or name_of(x.get("Investigation Phase")) != "Violation"
        ):
            continue
        c = {
            "inv": "337-TA-" + num.split("-", 1)[1],
            "case_id": x.get("Case ID"),
            "title": x.get("Topic") or x.get("Full Title"),
            "edis_docket": x.get("Docket Number"),
            "status": name_of(x.get("Investigation Status")),
            "complaint": mdy(x.get("Initiating Document Received Date")),
            "instituted": mdy(x.get("Start Date")),
            "noi_pub": mdy(x.get("Date of Publication of FR Notice (NOI)")),
            "hearing_start": mdy(x.get("Hearing/Conf Start Date")),
            "hearing_end": mdy(x.get("Hearing/Conf End Date")),
            "id_date": mdy(x.get("Initial Determination Date")),
            "id_type": name_of(x.get("Initial Determination Type")),
            "fd_date": mdy(x.get("Final Determination Date")),
            "fd_type": name_of(x.get("Final Determination Type")),
            "target": mdy(x.get("Target Date")),
            "terminated": mdy(x.get("Investigation Termination Date"))
            or mdy(x.get("Investigation End Date")),
            "orders": [
                o.get("Order Title") for o in x.get("Unfair Import Orders") or []
            ],
            "unfair_acts": sorted(
                {
                    name_of(u.get("Unfair Act in Notice"))
                    for u in x.get("Unfair Act") or []
                }
                - {None}
            ),
            "parties": [],
        }
        if not in_window(c):
            continue
        for p in x.get("Participants") or []:
            role = name_of(p.get("Participant Type"))
            nm = (p.get("Participant") or {}).get("Name") or ""
            disp = name_of(p.get("Participant Disposition"))
            if disp == "Participant Name Change":
                continue
            m = match_ticker(nm, aliases)
            c["parties"].append(
                {
                    "role": role,
                    "name": nm.strip(),
                    "country": name_of((p.get("Participant") or {}).get("Country")),
                    "disp": disp,
                    "disp_date": mdy(p.get("Participant Disposition Date")),
                    "default": p.get("Default"),
                    "ticker": m[0] if m else None,
                    "parent": m[1] if m else None,
                    "alias_note": m[2] if m else None,
                }
            )
        cases.append(c)
    (RAW / "cases_parsed.json").write_text(json.dumps(cases, default=str, indent=1))
    n_l = sum(any(p["ticker"] for p in c["parties"]) for c in cases)
    print(
        f"{len(cases)} investigations in window, {n_l} with a listed party",
        file=sys.stderr,
    )
    return cases


# ---------------------------------------------------------------- party rows
VIOL = {"Violation Found", "Summary Determination - Violation"}
NOVIOL = {"No Violation Found", "Summary Determination - No Violation"}
RANK = [
    *VIOL,
    *NOVIOL,
    "Consent Order",
    "Settlement",
    "Complaint Withdrawn",
    "Not Instituted",
    "Other",
    "Consolidated",
    None,
]
FINAL_ID = {
    "Final, Violation",
    "Final, No Violation",
    "Violation, Summary Determination",
    "No Violation, Summary Determination",
}
FD_SUBST = {"Violation", "No Violation"}
PHARMA = {"ABBV", "ALVO", "ASND", "BFRI", "BMRN", "GMAB", "IMGN", "LLY", "NVS", "REGN"}
PHARMA |= {"SNY", "TEVA", "VKTX"}


def resolve(rule: str, on: date | None) -> str | None:
    """'VLDR:2023-02-10:OUST' -> VLDR before that date, OUST from it."""
    parts = rule.split(":")
    t = parts[0]
    for i in range(1, len(parts) - 1, 2):
        if on and on >= date.fromisoformat(parts[i]):
            t = parts[i + 1]
    return None if t == "-" else t


def dd(v) -> date | None:
    return date.fromisoformat(v) if v else None


def is_open(c: dict) -> bool:
    return c["status"] not in TERMINAL


def complainant_outcome(c: dict) -> str:
    ds = {p["disp"] for p in c["parties"] if p["role"] == "Respondent"}
    v, nv = bool(ds & VIOL) or c["fd_type"] == "Violation", bool(ds & NOVIOL)
    if is_open(c) and c["fd_type"] not in FD_SUBST:
        return "pending"
    if v and nv:
        return "split"
    if v:
        return "win"
    if nv or c["fd_type"] == "No Violation":
        return "loss"
    if ds & {"Settlement", "Consent Order"}:
        return "settled"
    if "Complaint Withdrawn" in ds or c["status"] == "Complaint/Request Withdrawn":
        return "withdrawn"
    return "dismissed"


def respondent_outcome(c: dict, disp: str | None) -> str:
    disp = None if disp == "Consolidated" else disp
    if disp in VIOL:
        return "loss"
    if disp in NOVIOL:
        return "win"
    if disp in ("Settlement", "Consent Order"):
        return "settled"
    if disp == "Complaint Withdrawn":
        return "withdrawn"
    if disp == "Not Instituted":
        return "dismissed"
    if disp is None and is_open(c):
        return "pending"
    if c["fd_type"] == "Violation":
        return "loss"
    if c["fd_type"] == "No Violation":
        return "win"
    if c["status"] == "Complaint/Request Withdrawn":
        return "withdrawn"
    return "dismissed"


GOOD = {
    "Complainant": {"win": "good", "loss": "bad", "split": "mixed", "dismissed": "bad"},
    "Respondent": {"win": "good", "loss": "bad", "split": "mixed"},
}
GOOD["Respondent"] |= {"withdrawn": "good", "dismissed": "good"}


def decision_event(c: dict, role: str, disp: str | None) -> tuple[str, date | None]:
    disp = None if disp == "Consolidated" else disp
    fd, idd = dd(c["fd_date"]), dd(c["id_date"])
    final_id = c["id_type"] in FINAL_ID
    if role == "Respondent" and disp in VIOL | NOVIOL:
        if c["fd_type"] in FD_SUBST and fd:
            return "final determination", fd
        return "determination as to this respondent", dd(c["_disp_date"])
    if role == "Respondent" and disp:
        return "termination as to this respondent", dd(c["_disp_date"]) or dd(
            c["terminated"]
        )
    if c["fd_type"] in FD_SUBST and fd:
        return "final determination", fd
    if is_open(c):
        return ("initial determination", idd) if final_id and idd else ("pending", None)
    return "termination of investigation", dd(c["terminated"]) or fd


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, 28))


def known_in_advance(c: dict, kind: str, when: date | None) -> tuple[str, str]:
    tgt = dd(c["target"])
    if kind == "final determination":
        if tgt and when == tgt:
            return "yes", f"FD issued on the Commission's public target date {tgt}"
        return "no", f"FD on {when}; last public target date {tgt}"
    if kind == "initial determination" and tgt:
        due = add_months(tgt, -4)
        ok = abs((when - due).days) <= 7
        return ("yes" if ok else "no"), (
            f"final ID due about {due} (estimated as target date minus 4 months)"
        )
    return "no", "settlement/withdrawal terminations have no preset date"


def fr_index() -> dict[str, list[dict]]:
    p = RAW / "fr_docs.json"
    out: dict[str, list[dict]] = {}
    if not p.exists():
        return out
    for d in json.loads(p.read_text()):
        blob = " ".join([d.get("title") or "", " ".join(d.get("docket_ids") or [])])
        for n in set(re.findall(r"337-TA-(\d{3,4})", blob)):
            out.setdefault("337-TA-" + n, []).append(d)
    return out


def fr_source(notices: list[dict], when: date | None, kind: str) -> dict | None:
    """Earliest FR notice published within 45 days after the event, preferring
    one whose title names the event type."""
    if not when:
        return None
    want = "terminat" if "termination" in kind else "determination"

    def lag(d: dict) -> int:
        return (date.fromisoformat(d["publication_date"]) - when).days

    near = sorted((d for d in notices if 0 <= lag(d) <= 45), key=lag)
    named = [d for d in near if want in (d.get("title") or "").lower()]
    return (named or near or [None])[0]


# ---------------------------------------------------------------- prices
END = date(2026, 10, 14)
P1 = 1577836800  # 2020-01-01
P2 = int(time.mktime(END.timetuple())) + 86400
_PX: dict[str, dict | None] = {}


_YAHOO_DOWN = False


def _yahoo_blocked() -> bool:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=5d&interval=1d"
    return (
        requests.get(url, headers={"User-Agent": YAHOO_UA}, timeout=30).status_code
        == 429
    )


def yahoo(sym: str) -> dict | None:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?period1={P1}&period2={P2}&interval=1d&events=div%2Csplit"
    )
    global _YAHOO_DOWN
    if _YAHOO_DOWN:
        return None
    txt = get(url, "yahoo", tries=1)
    if not txt:
        # rate-limited (HTTP 429) or unknown symbol: stop asking this run
        _YAHOO_DOWN = not cache_path(url, "yahoo").exists() and _yahoo_blocked()
        return None
    r = (json.loads(txt).get("chart", {}).get("result") or [None])[0]
    if not r or not r.get("timestamp"):
        return None
    from datetime import datetime

    q = r["indicators"]["quote"][0]
    adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    rows = []
    for t, c, a, v in zip(r["timestamp"], q["close"], adj, q["volume"]):
        if c is None or a is None:
            continue
        rows.append((datetime.fromtimestamp(t, UTC).date(), c, a, v or 0))
    splits = [
        (
            datetime.fromtimestamp(s["date"], UTC).date(),
            s["numerator"] / s["denominator"],
        )
        for s in (r.get("events", {}).get("splits") or {}).values()
    ]
    return {"rows": rows, "splits": splits, "src": "Yahoo chart API"}


def polygon_daily(sym: str) -> dict | None:
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        return None
    a = date.fromordinal(END.toordinal() - 728)
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/{a}/{END}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={key}"
    )
    txt = get(url, "polygon_daily")
    res = json.loads(txt).get("results") if txt else None
    if not res:
        return None
    from datetime import datetime

    rows = [
        (datetime.fromtimestamp(b["t"] / 1000, UTC).date(), b["c"], b["c"], b["v"])
        for b in res
    ]
    return {"rows": rows, "splits": [], "src": "Polygon daily (last 2 years only)"}


def prices(sym: str) -> dict | None:
    if sym not in _PX:
        _PX[sym] = yahoo(sym) or polygon_daily(sym)
    return _PX[sym]


def raw_close(px: dict, i: int) -> float:
    """Yahoo closes are split-adjusted; undo later splits to match share counts."""
    d, c = px["rows"][i][0], px["rows"][i][1]
    for sd, ratio in px["splits"]:
        if sd > d:
            c *= ratio
    return c


def day_index(px: dict, d: date) -> int | None:
    for i, r in enumerate(px["rows"]):
        if r[0] >= d:
            return i
    return None


def window_ret(px: dict, d: date, n: int) -> tuple[float | None, int | None]:
    """Close of trading day (first on/after d) + n-1 vs the close before it."""
    i = day_index(px, d)
    if i is None or i == 0 or i + n - 1 >= len(px["rows"]):
        return None, i
    if (px["rows"][i][0] - d).days > 5:  # not trading then (pre-IPO or gap)
        return None, i
    return px["rows"][i + n - 1][2] / px["rows"][i - 1][2] - 1, i


def adv20(px: dict, i: int | None) -> float | None:
    if i is None or i < 20:
        return None
    return sum(raw_close(px, j) * px["rows"][j][3] for j in range(i - 20, i)) / 20


# ---------------------------------------------------------------- SEC
SEC_TICKERS = RAW / "sec_company_tickers_exchange.json"
EXTRA_CIK = {
    "CCMP": 1102934,
    "COMM": 1517228,
    "VISN": 1517228,
    "DISH": 1001082,
    "HOLX": 859737,
    "IMGN": 855654,
    "IRBT": 1159167,
    "JNPR": 1043604,
    "LEG": 58492,
    "MASI": 937556,
    "QRTEA": 1355096,
    "QVCGA": 1355096,
    "SATS": 1415404,
    "SKX": 1065837,
    "VLDR": 1745317,
    "VVNT": 1713952,
    "VZIO": 1835591,
}


def cik_of(sym: str) -> int | None:
    if sym in EXTRA_CIK:
        return EXTRA_CIK[sym]
    if not SEC_TICKERS.exists():
        SEC_TICKERS.write_text(
            get("https://www.sec.gov/files/company_tickers_exchange.json")
        )
    j = json.loads(SEC_TICKERS.read_text())
    f = j["fields"]
    for r in j["data"]:
        if r[f.index("ticker")] == sym:
            return r[f.index("cik")]
    return None


def companyfacts(cik: int) -> dict:
    txt = get(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", "sec_facts"
    )
    return json.loads(txt) if txt else {}


def shares_at(facts: dict, d: date) -> int | None:
    units = (
        facts.get("facts", {})
        .get("dei", {})
        .get("EntityCommonStockSharesOutstanding", {})
    )
    vals = [v for v in units.get("units", {}).get("shares", []) if dd(v["filed"]) <= d]
    if not vals:
        return None
    last = max(v["end"] for v in vals)
    # multi-class issuers report one fact per class with the same date; add them
    same = {v["val"] for v in vals if v["end"] == last}
    return sum(same)


REV_TAGS = [
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "Revenues"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ("us-gaap", "SalesRevenueNet"),
    ("ifrs-full", "Revenue"),
]


def revenue_ttm(facts: dict, d: date) -> tuple[float | None, str]:
    best: tuple[date, float, str] | None = None
    for ns, tag in REV_TAGS:
        units = facts.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {})
        vals = [
            v for v in units.get("USD", []) if v.get("start") and dd(v["filed"]) <= d
        ]
        if not vals:
            continue
        span = lambda v: (dd(v["end"]) - dd(v["start"])).days
        annual = [v for v in vals if 350 <= span(v) <= 380]
        if not annual:
            continue
        a = max(annual, key=lambda v: (v["end"], v["filed"]))
        ttm, how = a["val"], f"{tag} fiscal year to {a['end']}"
        ytd = [v for v in vals if v["start"] > a["end"] and span(v) < 350]
        if ytd:
            y = max(ytd, key=lambda v: (v["end"], v["filed"]))
            prior = [
                v
                for v in vals
                if abs((dd(v["end"]) - add_months(dd(y["end"]), -12)).days) <= 7
                and abs(span(v) - span(y)) <= 7
            ]
            if prior:
                ttm = a["val"] + y["val"] - prior[0]["val"]
                how = f"{tag} TTM to {y['end']}"
        end = dd(how.split(" to ")[-1])
        if not best or end > best[0]:
            best = (end, ttm, how)
    return (
        (best[1], best[2]) if best else (None, "no USD revenue in XBRL before filing")
    )


# ---------------------------------------------------------------- timing
def to_et(utc_iso: str):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    t = datetime.fromisoformat(utc_iso)
    return t.astimezone(ZoneInfo("America/New_York"))


_SUBS: dict[int, dict[str, str]] = {}


def acceptance_times(cik: int) -> dict[str, str]:
    """accession -> EDGAR acceptance time (UTC in the JSON; checked against index pages)."""
    if cik in _SUBS:
        return _SUBS[cik]
    base = "https://data.sec.gov/submissions/"
    txt = get(f"{base}CIK{cik:010d}.json", "sec_subs")
    out: dict[str, str] = {}
    if txt:
        j = json.loads(txt)
        parts = [j["filings"]["recent"]]
        for f in j["filings"].get("files", []):
            if f["filingTo"] >= "2020-06-01":
                t2 = get(base + f["name"], "sec_subs")
                if t2:
                    parts.append(json.loads(t2))
        for p in parts:
            out.update(zip(p["accessionNumber"], p["acceptanceDateTime"]))
    _SUBS[cik] = out
    return out


def earnings_times(cik: int) -> list:
    """ET acceptance times of the company's 8-K earnings releases (Item 2.02)."""
    base = "https://data.sec.gov/submissions/"
    txt = get(f"{base}CIK{cik:010d}.json", "sec_subs")
    if not txt:
        return []
    j = json.loads(txt)
    parts = [j["filings"]["recent"]]
    for f in j["filings"].get("files", []):
        if f["filingTo"] >= "2020-06-01":
            t2 = get(base + f["name"], "sec_subs")
            if t2:
                parts.append(json.loads(t2))
    return [
        to_et(t)
        for p in parts
        for t, it in zip(p["acceptanceDateTime"], p["items"])
        if "2.02" in (it or "")
    ]


def company_release(cik: int, when: date) -> tuple[str, str] | None:
    """Earliest 8-K/6-K mentioning the ITC filed from the day before to 3 days after."""
    a, b = (
        date.fromordinal(when.toordinal() - 1),
        date.fromordinal(when.toordinal() + 3),
    )
    q = urllib.parse.urlencode(
        {
            "q": '"International Trade Commission"',
            "forms": "8-K,6-K",
            "dateRange": "custom",
            "startdt": a.isoformat(),
            "enddt": b.isoformat(),
            "ciks": f"{cik:010d}",
        }
    )
    txt = get("https://efts.sec.gov/LATEST/search-index?" + q, "sec_efts")
    if not txt:
        return None
    hits = json.loads(txt).get("hits", {}).get("hits", [])
    acc = acceptance_times(cik)
    best = None
    for h in hits:
        adsh, fn = h["_id"].split(":", 1)
        t = acc.get(adsh)
        if not t:
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fn}"
        if not best or t < best[0]:
            best = (t, url)
    if not best:
        return None
    return to_et(best[0]).strftime("%Y-%m-%d %H:%M"), best[1]


def market_hours(t) -> str:
    if t.weekday() >= 5:
        return "no"
    m = t.hour * 60 + t.minute
    return "yes" if 570 <= m < 960 else "no"


def half_move_time(sym: str, px: dict, i: int) -> str | None:
    """Clock time (ET) when the stock first covered half of trading day i's
    close-to-close move, from Polygon 1-minute bars incl. pre-market."""
    from datetime import datetime

    key = os.environ.get("POLYGON_API_KEY")
    d = px["rows"][i][0]
    if not key or (END - d).days > 725:
        return None
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/{d}/{d}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={key}"
    )
    txt = get(url, "polygon_min")
    bars = json.loads(txt).get("results") if txt else None
    if not bars:
        return None
    prev, close = px["rows"][i - 1][1], px["rows"][i][1]
    move = close - prev
    if move == 0:
        return None
    for b in bars:
        if (b["c"] - prev) / move >= 0.5:
            t = datetime.fromtimestamp(b["t"] / 1000, UTC).isoformat()
            return to_et(t).strftime("%Y-%m-%d %H:%M")
    return None


# ---------------------------------------------------------------- build rows
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

# Rows read by hand against the Commission notice / ID (case_id -> finding).
HAND_CHECKED: dict[str, str] = {
    # read against the Commission's Federal Register notices (cached in raw/)
    "337-TA-1276-AAPL-R": "FD of violation on the 2023-10-26 target date "
    "(FR notice 2023-11-01); exclusion order on Apple Watch Series 9/Ultra 2.",
    "337-TA-1276-MASI-C": "Masimo complainant; FD of violation 2023-10-26 "
    "(FR notice 2023-11-01).",
    "337-TA-1252-IRBT-C": "iRobot complainant; FD of violation 2023-03-21 "
    "(FR notice 2023-03-27).",
    "337-TA-1252-SN-R": "SharkNinja respondent; FD of violation 2023-03-21 "
    "(FR notice 2023-03-27). SharkNinja listed only from 2023-07-31.",
    "337-TA-1266-AAPL-R": "AliveCor (private) v Apple; FD of violation 2022-12-22 "
    "(FR notice 2022-12-30), order held pending patent appeals.",
    "337-TA-1191-GOOGL-R": "Sonos v Google; FD of violation 2022-01-06 "
    "(FR notice 2022-01-12).",
    "337-TA-1191-SONO-C": "Sonos complainant; FD of violation 2022-01-06 "
    "(FR notice 2022-01-12).",
    "337-TA-1365-SHLS-C": "FD of no violation 2025-01-14, a day before the "
    "2025-01-15 target date, reversing the judge's violation ID (FR notice "
    "2025-01-21).",
    "337-TA-1438-SHLS-C": "FD of violation and exclusion order against Voltage "
    "2026-06-25 on the target date (FR notice 2026-06-30).",
    "337-TA-1400-GPRO-C": "FD of violation against Insta360 2026-02-26 on the "
    "target date (FR notice 2026-03-03).",
    "337-TA-1380-NOK-C": "Terminated 2025-04-23 on a joint motion based on "
    "settlement with Amazon and HP (FR notice 2025-04-29); settlement terms "
    "not public.",
}
# Hand corrections after reading notices: case_id -> {column: value}
OVERRIDES: dict[str, dict[str, str]] = {}


def fmt(x: float | None, nd: int = 4) -> str:
    return "" if x is None else f"{x:.{nd}f}"


def group_parties(c: dict) -> list[dict]:
    """Merge subsidiaries of one listed parent into one party per role."""
    out: dict[tuple[str, str], dict] = {}
    for p in c["parties"]:
        if not p["ticker"] or p["role"] not in ("Complainant", "Respondent"):
            continue
        g = out.setdefault(
            (p["ticker"], p["role"]),
            {
                "rule": p["ticker"],
                "role": p["role"],
                "parent": p["parent"],
                "names": [],
                "disps": [],
                "dates": [],
                "note": p["alias_note"],
                "default": False,
            },
        )
        g["names"].append(p["name"])
        g["disps"].append(p["disp"])
        if p["disp_date"]:
            g["dates"].append(p["disp_date"])
        g["default"] |= bool(p["default"])
    for g in out.values():
        g["disp"] = min(g["disps"], key=RANK.index)
        g["disp_date"] = max(g["dates"]) if g["dates"] else None
    return list(out.values())


_SUFFIX = re.compile(
    r"[,.]?\s+(inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|plc|"
    r"n\.v|b\.v|ag|gmbh|s\.a|a/s|lp|l\.p|holdings?)\b.*$",
    re.IGNORECASE,
)


def fr_check(
    notices: list[dict], names: list[str], outcome: str, role: str
) -> tuple[bool, bool]:
    """Does any Federal Register notice for the investigation name this party,
    and does the notice wording agree with the outcome taken from IDS?"""
    text = " ".join((n.get("text") or "") for n in notices).lower()
    text = re.sub(r"\s+", " ", text)
    titles = " ".join(n["title"] for n in notices).lower()
    cores = {_SUFFIX.sub("", n).strip().lower() for n in names}
    name_ok = any(len(k) >= 3 and k in text for k in cores)
    viol = "violation of section 337" in titles.replace("no violation", "")
    noviol = "no violation" in titles
    comp = role == "Complainant"
    words = {
        "win": viol if comp else noviol,
        "loss": noviol if comp else viol,
        "dismissed": "no violation" in text or "terminat" in text,
        "settled": "settlement" in text or "consent order" in text,
        "withdrawn": "withdraw" in text,
        "split": True,
        "pending": True,
    }
    return name_ok, words.get(outcome, False)


def stage_rows() -> None:
    import csv

    cases = json.loads((RAW / "cases_parsed.json").read_text())
    frx = fr_index()
    spy, xbi = prices("SPY"), prices("XBI")
    rows, skipped = [], []
    for c in cases:
        groups = group_parties(c)
        comp_names = [p["name"] for p in c["parties"] if p["role"] == "Complainant"]
        resp_names = [p["name"] for p in c["parties"] if p["role"] == "Respondent"]
        for g in groups:
            c["_disp_date"] = g["disp_date"]
            role = g["role"]
            if role == "Complainant":
                outcome = complainant_outcome(c)
            else:
                outcome = respondent_outcome(c, g["disp"])
            kind, when = decision_event(
                c, role, g["disp"] if role == "Respondent" else None
            )
            filed = dd(c["complaint"]) or dd(c["instituted"])
            sym = resolve(g["rule"], when or END)
            sym_f = resolve(g["rule"], filed) if filed else None
            if not sym and not sym_f:
                skipped.append(
                    (c["inv"], g["parent"], "not listed at decision or filing")
                )
                continue
            sym = sym or sym_f
            others = [x for x in groups if x["role"] != role]
            notes = []
            ev = [f"complaint {c['complaint']}", f"instituted {c['instituted']}"]
            if c["hearing_start"]:
                ev.append(
                    f"evidentiary hearing {c['hearing_start']} to {c['hearing_end']}"
                )
            if c["id_date"]:
                ev.append(f"ID {c['id_date']} ({c['id_type']})")
            if c["fd_date"]:
                ev.append(f"Commission FD {c['fd_date']} ({c['fd_type']})")
            if c["fd_type"] == "Violation" and c["fd_date"]:
                pr = date.fromordinal(dd(c["fd_date"]).toordinal() + 60)
                ev.append(
                    f"presidential review ends about {pr} (FD + 60 days, computed)"
                )
            if c["orders"]:
                ev.append("orders: " + "; ".join(sorted(set(c["orders"]))))
            if c["target"]:
                ev.append(f"target date {c['target']}")
            if c["terminated"]:
                ev.append(f"terminated {c['terminated']}")
            ev.append(f"status {c['status']}")
            notes.append("Events: " + ", ".join(e for e in ev if "None" not in e) + ".")
            notes.append(
                f"{g['parent']} entities: {'; '.join(sorted(set(g['names'])))[:200]}; "
                f"IDS disposition {g['disp'] or 'none yet'}"
                + (f" on {g['disp_date']}" if g["disp_date"] else "")
                + (" (found in default)" if g["default"] else "")
                + "."
            )
            if g["note"]:
                notes.append(f"Ticker note: {g['note']}.")
            if outcome == "pending" and kind == "initial determination":
                notes.append(
                    f"Judge's ID ({c['id_type']}) issued; Commission decision pending."
                )
            adv_yes, adv_note = known_in_advance(c, kind, when) if when else ("", "")
            if adv_note:
                notes.append(adv_note + ".")
            ofc = GOOD[role].get(outcome, "unknown")
            if outcome == "pending" and kind == "initial determination":
                good_id = ("No Violation" in c["id_type"]) == (role == "Respondent")
                ofc = "good" if good_id else "bad"
                notes.append("outcome_for_company reflects the ID only.")
            fr = fr_source(frx.get(c["inv"], []), when, kind)
            name_ok, out_ok = fr_check(frx.get(c["inv"], []), g["names"], outcome, role)
            conf = "medium" if name_ok and out_ok else "low"
            notes.append(
                "Automatic check of Federal Register notices: party named "
                f"{'yes' if name_ok else 'no'}, outcome wording agrees "
                f"{'yes' if out_ok else 'no'} (not a hand check)."
            )
            bench_sym = "XBI" if sym in PHARMA else "SPY"
            bench = xbi if sym in PHARMA else spy
            px = prices(sym)
            r = {k: "" for k in COLS}
            r.update(
                case_id=f"{c['inv']}-{sym}-{role[0]}",
                case_type="ITC Section 337",
                case_name=f"In the Matter of {c['title']}",
                court=COURT,
                docket_number=f"{c['inv']} (EDIS docket {c['edis_docket']})",
                docket_url=CASE_URL.format(c["case_id"]),
                ticker=sym,
                company=g["parent"],
                company_role=role.lower(),
                counterparty="; ".join(
                    sorted(
                        {
                            x
                            for x in (
                                resp_names if role == "Complainant" else comp_names
                            )
                        }
                    )
                )[:300],
                counterparty_ticker=";".join(
                    sorted(
                        {resolve(x["rule"], when or END) or "" for x in others} - {""}
                    )
                ),
                filed_date=str(filed or ""),
                trial_start_date=c["hearing_start"] or "",
                trial_end_date=c["hearing_end"] or "",
                decision_date=str(when or ""),
                decision_known_in_advance=adv_yes,
                decision_source_url=(fr or {}).get("html_url")
                or CASE_URL.format(c["case_id"]),
                outcome=outcome,
                outcome_for_company=ofc,
                days_filed_to_decision=str((when - filed).days)
                if when and filed
                else "",
                confidence=conf,
                first_public_source=(
                    "USITC EDIS (Commission notice or ALJ order, posted by the Secretary)"
                    if when
                    else ""
                ),
                first_public_time_et=str(when or ""),
                time_precision="day" if when else "",
                during_market_hours="unknown" if when else "",
                minute_data_available="no",
            )
            srcs = [CASE_URL.format(c["case_id"])]
            if fr:
                srcs.append(fr["html_url"])
            if px:
                srcs.append(px["src"])
            if not px:
                notes.append(
                    f"No daily prices for {sym}: Yahoo was rate-limited this run and "
                    "Polygon free covers 2 years; delisted symbols may also be missing."
                )
            else:
                if filed:
                    rf, i_f = window_ret(px, filed, 2)
                    bf, _ = window_ret(bench, filed, 2) if bench else (None, None)
                    r["ret_filing_day"] = fmt(rf)
                    r["abn_ret_filing_day"] = fmt(
                        rf - bf if rf is not None and bf is not None else None
                    )
                    cik = cik_of(sym_f or sym)
                    facts = companyfacts(cik) if cik else {}
                    sh = shares_at(facts, filed) if facts else None
                    if sh and rf is not None:
                        r["market_cap_usd_at_filing"] = f"{sh * raw_close(px, i_f):.0f}"
                    rev, how = (
                        revenue_ttm(facts, filed) if facts else (None, "no SEC XBRL")
                    )
                    r["revenue_ttm_usd_at_filing"] = fmt(rev, 0)
                    notes.append(f"Revenue: {how}.")
                    if not sh or rf is None:
                        notes.append(
                            "Market cap blank: no dei shares-outstanding fact before filing."
                            if not sh
                            else "Market cap blank: no price on the filing date."
                        )
                if when:
                    rd, i_d = window_ret(px, when, 2)
                    bd, _ = window_ret(bench, when, 2) if bench else (None, None)
                    r5, _ = window_ret(px, when, 6)
                    r["ret_decision_day"] = fmt(rd)
                    r["abn_ret_decision_day"] = fmt(
                        rd - bd if rd is not None and bd is not None else None
                    )
                    r["ret_decision_plus5"] = fmt(r5)
                    a = adv20(px, i_d) if rd is not None else None
                    r["adv_usd_20d_before_decision"] = fmt(a, 0)
                    if rd is None:
                        notes.append(
                            f"No {sym} daily price around {when} from the sources "
                            "reachable this run (Yahoo was rate-limited; Polygon "
                            "free covers 2 years)."
                        )
                    elif i_d is not None and i_d + 1 < len(px["rows"]):
                        # the larger of the two days' moves is where the news landed
                        r1 = px["rows"][i_d][2] / px["rows"][i_d - 1][2] - 1
                        r2 = px["rows"][i_d + 1][2] / px["rows"][i_d][2] - 1
                        j = i_d if abs(r1) >= abs(r2) else i_d + 1
                        big = max(abs(r1), abs(r2)) >= 0.02
                        hm = half_move_time(sym, px, j) if big else None
                        if hm:
                            r["minute_data_available"] = "yes"
                            notes.append(
                                f"Minute bars: half of the {px['rows'][j][0]} move was done by "
                                f"{hm[11:]} ET (estimate of when the news reached the market)."
                            )
                    cik_d = cik_of(sym)
                    if cik_d:
                        for t in earnings_times(cik_d):
                            if -2 <= (t.date() - when).days <= 3:
                                notes.append(
                                    "Possible confounder: earnings 8-K (Item 2.02) "
                                    f"accepted {t:%Y-%m-%d %H:%M} ET, so the move may "
                                    "be about earnings, not this case."
                                )
                                break
                    rel = company_release(cik_d, when) if cik_d else None
                    if rel:
                        r["company_release_time_et"] = rel[0]
                        srcs.append(rel[1])
                        notes.append(
                            "Company 8-K/6-K mentioning the ITC accepted by EDGAR at "
                            f"{rel[0]} ET (not checked to be about this case unless hand-checked)."
                        )
                    if (
                        c["id_date"]
                        and kind == "final determination"
                        and dd(c["id_date"]) >= START
                    ):
                        ri, _ = window_ret(px, dd(c["id_date"]), 2)
                        bi, _ = (
                            window_ret(bench, dd(c["id_date"]), 2)
                            if bench
                            else (None, None)
                        )
                        if ri is not None and bi is not None:
                            notes.append(
                                f"ID-day 2-day abnormal return {ri - bi:+.4f}."
                            )
            notes.append(
                f"Times unknown, so filing and decision returns are 2-day close-to-close "
                f"(event day + next trading day); benchmark {bench_sym}."
            )
            notes.append(
                "revenue_at_stake blank: product revenue at issue not disclosed."
            )
            r["sources"] = " | ".join(srcs)
            r["notes"] = " ".join(notes)
            if r["case_id"] in HAND_CHECKED:
                r["confidence"] = "high"
                r["notes"] = (
                    "Hand check: " + HAND_CHECKED[r["case_id"]] + " " + r["notes"]
                )
            r.update(OVERRIDES.get(r["case_id"], {}))
            dup = next((x for x in rows if x["case_id"] == r["case_id"]), None)
            if dup:
                # two listed parents resolve to one ticker (e.g. NJOY into Altria)
                dup["company"] += " + " + r["company"]
                dup["notes"] += " Also covers " + r["company"] + "."
                continue
            rows.append(r)
    rows.sort(key=lambda r: (r["decision_date"] or "9999", r["case_id"]))
    with open(OUT / "cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    (RAW / "skipped_parties.json").write_text(json.dumps(skipped, indent=1))
    print(
        f"{len(rows)} rows, {len(skipped)} listed-later parties skipped",
        file=sys.stderr,
    )


def stage_stats() -> None:
    """Print the numbers quoted in docs/universe_itc337.md."""
    import csv
    import statistics as st
    from collections import Counter

    cases = json.loads((RAW / "cases_parsed.json").read_text())
    rows = list(csv.DictReader((OUT / "cases.csv").read_text().splitlines()))
    print("investigations in window:", len(cases))
    inst = Counter((c["instituted"] or "none")[:4] for c in cases)
    print("instituted per year:", sorted(inst.items()))
    print("status:", Counter(c["status"] for c in cases).most_common())
    listed = {r["case_id"].rsplit("-", 2)[0] for r in rows}
    print("investigations with a listed party (rows exist):", len(listed))
    print("rows:", len(rows), Counter(r["company_role"] for r in rows))
    print("outcome:", Counter(r["outcome"] for r in rows).most_common())
    print("outcome_for_company:", Counter(r["outcome_for_company"] for r in rows))
    print("known in advance:", Counter(r["decision_known_in_advance"] for r in rows))
    print("confidence:", Counter(r["confidence"] for r in rows))
    ab = [
        (abs(float(r["abn_ret_decision_day"])), r)
        for r in rows
        if r["abn_ret_decision_day"]
    ]
    print("rows with decision-day abnormal return:", len(ab))
    for t in (0.05, 0.10, 0.25):
        print(f"  |abn| > {t:.0%}:", sum(a > t for a, _ in ab))
    if ab:
        print("  median |abn|:", round(st.median(a for a, _ in ab), 4))
    print("top 10 |abn| decision day:")
    for a, r in sorted(ab, key=lambda x: -x[0])[:10]:
        print(
            f"  {r['ticker']} {r['case_id']} {r['decision_date']} abn {r['abn_ret_decision_day']}"
            f" ret {r['ret_decision_day']} {r['outcome']}/{r['outcome_for_company']}"
            f" adv={r['decision_known_in_advance']} cap={r['market_cap_usd_at_filing']}"
        )
    print("minute data rows:", sum(r["minute_data_available"] == "yes" for r in rows))
    uns = [r for r in rows if r["decision_known_in_advance"] == "no"]
    print("unscheduled rows:", len(uns))
    hm = []
    for r in rows:
        m = re.search(r"move was done by (\d\d):(\d\d) ET", r["notes"])
        if m:
            mins = int(m.group(1)) * 60 + int(m.group(2))
            hm.append((r, mins, 585 <= mins < 960))
    print(
        "half-move during market hours (all / unscheduled):",
        sum(x[2] for x in hm),
        "/",
        sum(x[2] for x in hm if x[0]["decision_known_in_advance"] == "no"),
        "of",
        len(hm),
    )
    rel = [r for r in rows if r["company_release_time_et"]]
    rel_mh = [
        r
        for r in rel
        if 570
        <= int(r["company_release_time_et"][11:13]) * 60
        + int(r["company_release_time_et"][14:16])
        < 960
    ]
    print("company 8-K/6-K found:", len(rel), "during market hours:", len(rel_mh))
    conf = [r for r in rows if "Possible confounder" in r["notes"]]
    print("rows with an earnings 8-K near the decision:", len(conf))
    clean = [(a, r) for a, r in ab if "Possible confounder" not in r["notes"]]
    for t in (0.05, 0.10, 0.25):
        print(
            f"  no-earnings rows |abn| > {t:.0%}:",
            sum(a > t for a, _ in clean),
            "of",
            len(clean),
        )
    if clean:
        print("  no-earnings median |abn|:", round(st.median(a for a, _ in clean), 4))
    hm = [x for x in hm if "Possible confounder" not in x[0]["notes"]]
    print(
        "fast candidates (unscheduled, half-move in market hours, no earnings), by |abn|:"
    )
    cand = [
        (abs(float(r["abn_ret_decision_day"] or 0)), r, m)
        for r, m, ok in hm
        if ok and r["decision_known_in_advance"] == "no"
    ]
    for a, r, m in sorted(cand, key=lambda x: -x[0])[:10]:
        print(
            f"  {r['ticker']} {r['case_id']} {r['decision_date']} abn {r['abn_ret_decision_day']} half-move {m // 60:02d}:{m % 60:02d} rel {r['company_release_time_et']}"
        )


if __name__ == "__main__":
    stages = sys.argv[1:] or ["ids", "parse"]
    for s in stages:
        globals()["stage_" + s]()
