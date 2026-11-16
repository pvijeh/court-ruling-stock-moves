"""Database of lawsuit rulings that moved a stock, with the court's filing time.

For each candidate (ticker, court, case-name words, approximate date) we search the
free RECAP archive (CourtListener) for opinions, orders, verdicts and judgments
filed in a window around the date. For each entry we read the filing clock time
from its public document page, and the stock's one-day move from Yahoo daily bars:
same-day close vs prior close if filed before 4 pm ET, else next close vs that day's
close. The entry with the largest absolute move is kept.

Output: data/lawsuit_moves.csv
"""

import csv
import html
import json
import re
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from common import DATA, get

ET = ZoneInfo("America/New_York")
CL = "https://www.courtlistener.com"
KINDS = re.compile(
    r"(?i)\b(opinion|memorandum|order|verdict|judgment|findings|injunction|ruling)\b"
)
SKIP = re.compile(
    r"(?i)^\s*(sealed|oral order|so ordered|order granting.*(extend|leave|seal)|minute order)"
)
# (tickers, court id, case-name query, approximate date, +/- days, note)
CANDIDATES = [
    (
        "LQDA UTHR",
        "ded",
        "United Therapeutics AND Liquidia",
        "2026-09-30",
        0,
        "YUTREPIA '327 trial opinion",
    ),
    (
        "GOOGL AAPL",
        "dcd",
        '"United States" AND Google',
        "2025-09-02",
        0,
        "search antitrust remedies",
    ),
    (
        "GOOGL",
        "dcd",
        '"United States" AND Google',
        "2024-08-05",
        0,
        "search antitrust liability",
    ),
    (
        "GOOGL",
        "vaed",
        '"United States" AND Google',
        "2025-04-17",
        0,
        "ad tech liability",
    ),
    (
        "CPRI TPR",
        "nysd",
        '"Federal Trade Commission" AND Tapestry',
        "2024-10-24",
        1,
        "Tapestry-Capri merger blocked",
    ),
    (
        "KR ACI",
        "ord",
        '"Federal Trade Commission" AND Kroger',
        "2024-12-10",
        1,
        "Kroger-Albertsons blocked",
    ),
    (
        "JBLU",
        "mad",
        '"United States" AND JetBlue AND Spirit',
        "2024-01-16",
        1,
        "JetBlue-Spirit blocked",
    ),
    (
        "META",
        "dcd",
        '"Federal Trade Commission" AND Meta',
        "2025-11-18",
        2,
        "FTC v Meta monopoly ruling",
    ),
    ("AAPL", "cand", "Epic AND Apple", "2025-04-30", 1, "Epic v Apple contempt order"),
    ("CORT", "njd", "Corcept AND Teva", "2023-12-29", 4, "Korlym patent trial"),
    ("JAZZ", "ded", "Jazz AND Avadel", "2024-08-27", 14, "Lumryz injunction"),
    (
        "REGN",
        "wvnd",
        "Regeneron AND Amgen",
        "2024-09-23",
        5,
        "Eylea biosimilar injunction denied",
    ),
    (
        "REGN",
        "wvnd",
        "Regeneron AND Mylan",
        "2024-06-11",
        5,
        "Eylea biosimilar injunction",
    ),
    ("NLST MU", "txed", "Netlist AND Micron", "2024-05-23", 3, "jury verdict $445M"),
    ("NLST", "txed", "Netlist AND Samsung", "2024-11-22", 5, "jury verdict $118M"),
    ("MASI AAPL", "cacd", "Masimo AND Apple", "2025-11-14", 3, "jury verdict $634M"),
    ("JNJ", "txsb", '"Red River Talc"', "2025-03-31", 2, "talc bankruptcy dismissed"),
    ("EXEL", "ded", "Exelixis AND MSN", "2024-09-25", 30, "Cabometyx patent ruling"),
    ("PCRX", "njd", "Pacira AND eVenus", "2024-08-09", 10, "Exparel patent ruling"),
    ("NVS", "ded", "Entresto", "2025-07-11", 0, "Entresto trial opinion"),
    (
        "LNTH",
        "ded",
        "Advanced Accelerator AND Lantheus",
        "2026-06-17",
        1,
        "Pluvicto/Lutathera opinion",
    ),
    ("VRTX", "ded", "Vertex AND Lupin", "2026-08-24", 1, "Vertex patent opinion"),
    ("AZN", "ded", "Acerta AND Cipla", "2025-11-25", 1, "Calquence patent opinion"),
    ("ACAD", "ded", "ACADIA AND Aurobindo", "2025-05-16", 3, "Nuplazid patent opinion"),
    ("MNK", "ded", "Mallinckrodt AND Airgas", "2025-02-12", 1, "INOmax patent opinion"),
    ("PFE", "ded", "Pfizer AND Cipla", "2026-03-10", 1, "Pfizer patent opinion"),
    ("NVO", "ded", '"Novo Nordisk" AND Mylan', "2025-07-22", 1, "Novo patent opinion"),
    (
        "NTRA NEO",
        "ncmd",
        "Natera AND NeoGenomics",
        "2023-12-27",
        5,
        "RaDaR preliminary injunction",
    ),
    (
        "NTRA GH",
        "cand",
        "Guardant AND Natera",
        "2024-03-29",
        5,
        "false-advertising verdict $292M",
    ),
    (
        "ABUS MRNA",
        "ded",
        "Arbutus AND Moderna",
        "2024-03-14",
        30,
        "LNP patent claim construction",
    ),
    ("VNDA", "dcd", "Vanda AND Food", "2025-01-01", 200, "Vanda v FDA rulings"),
    ("HRMY", "ded", "Harmony AND Lupin", "2026-01-01", 270, "Wakix patent opinion"),
    ("SUPN", "ded", "Supernus", "2025-06-01", 240, "Supernus patent opinion"),
    ("TEVA", "ded", "Teva AND Amneal", "2024-06-01", 180, "inhaler Orange Book case"),
    (
        "AMRN",
        "nvd",
        "Amarin AND Hikma",
        "2025-06-01",
        240,
        "Vascepa induced infringement",
    ),
    ("BHC", "ded", "Salix AND Norwich", "2024-06-01", 240, "Xifaxan patent"),
    ("INCY", "ded", "Incyte", "2025-06-01", 300, "Incyte patent opinion"),
    ("ARGX", "ded", "Halozyme", "2025-06-01", 300, "Halozyme patent case"),
    ("SAGE BIIB", "ded", "Sage", "2025-06-01", 300, "Sage patent case"),
    ("CYTK", "ded", "Cytokinetics", "2025-06-01", 300, "Cytokinetics case"),
]
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1d&range=3y"
_px: dict[str, dict[date, float]] = {}


def closes(sym: str) -> dict[date, float]:
    if sym not in _px:
        try:
            res = json.loads(get(YAHOO.format(s=sym)))["chart"]["result"][0]
            q = res["indicators"]["quote"][0]["close"]
            _px[sym] = {
                datetime.fromtimestamp(t, UTC).astimezone(ET).date(): c
                for t, c in zip(res["timestamp"], q)
                if c is not None
            }
        except (ValueError, KeyError, TypeError, IndexError):
            _px[sym] = {}
    return _px[sym]


def one_day_move(sym: str, t: datetime) -> float | None:
    px = closes(sym)
    days = sorted(px)
    d = t.date()
    if t.hour >= 16:
        d += timedelta(days=1)
    after = [x for x in days if x >= d]
    if not after:
        return None
    i = days.index(after[0])
    if i == 0:
        return None
    return round(100 * (px[days[i]] / px[days[i - 1]] - 1), 1)


def entries(court: str, name: str, d0: date, span: int) -> list[dict]:
    lo, hi = d0 - timedelta(days=span), d0 + timedelta(days=span)
    parts = [
        x if x.startswith('"') or " " not in x else f'"{x}"'
        for x in name.split(" AND ")
    ]
    q = f"caseName:({' AND '.join(parts)}) AND entry_date_filed:[{lo}T00:00:00Z TO {hi}T23:59:59Z]"
    url = f"{CL}/api/rest/v4/search/?" + urllib.parse.urlencode(
        {"type": "rd", "q": q, "court": court, "order_by": "entry_date_filed asc"}
    )
    try:
        res = json.loads(get(url))["results"]
    except (ValueError, KeyError):
        return []
    out = []
    for e in res:
        desc = e.get("description") or e.get("short_description") or ""
        if e.get("absolute_url") and KINDS.search(desc) and not SKIP.search(desc):
            out.append(
                {
                    "case": e.get("caseName", ""),
                    "docket": e.get("docketNumber", ""),
                    **e,
                }
            )
    return out


def filed_time(path: str) -> datetime | None:
    txt = html.unescape(re.sub(r"<[^>]+>", " ", get(CL + path)))
    m = re.search(
        r"Date Filed:\s*([A-Z][a-z]+\.? \d{1,2})[a-z]{2}, (\d{4}), (\d{1,2}:\d{2}) ([ap])\.m\.",
        txt,
    )
    if not m:
        return None
    s = f"{m.group(1).replace('.', '')} {m.group(2)} {m.group(3)} {m.group(4).upper()}M"
    return datetime.strptime(s, "%B %d %Y %I:%M %p").replace(tzinfo=ET)


def main() -> None:
    rows = []
    for tickers, court, name, day, span, note in CANDIDATES:
        best = None
        for e in entries(court, name, date.fromisoformat(day), span)[:15]:
            t = filed_time(e["absolute_url"])
            timed = t is not None
            if t is None:
                d = date.fromisoformat(str(e.get("entry_date_filed"))[:10])
                t = datetime(d.year, d.month, d.day, 12, tzinfo=ET)
            moves = {s: one_day_move(s, t) for s in tickers.split()}
            top = max((abs(v) for v in moves.values() if v is not None), default=None)
            # prefer entries with a known clock time, then the biggest move
            if top is not None and (best is None or (timed, top) > (best[4], best[0])):
                best = (top, e, t, moves, timed)
        row = {"tickers": tickers, "court": court, "note": note}
        if best:
            _, e, t, moves, timed = best
            row.update(
                case=e["case"][:90],
                docket=e["docket"],
                document_number=e.get("document_number") or "",
                description=(e.get("description") or "")[:160],
                filed_et=t.isoformat() if timed else t.date().isoformat(),
                clock_time_known=timed,
                market_hours=9 <= t.hour + t.minute / 60 < 16 and t.weekday() < 5,
                one_day_move_pct=" ".join(f"{s}:{v}" for s, v in moves.items()),
                max_abs_move_pct=best[0],
                url=CL + e["absolute_url"],
            )
        rows.append(row)
        print(
            tickers,
            row.get("filed_et", "-"),
            row.get("one_day_move_pct", "-"),
            flush=True,
        )
    fields = [
        "tickers",
        "court",
        "note",
        "case",
        "docket",
        "document_number",
        "description",
        "filed_et",
        "clock_time_known",
        "market_hours",
        "one_day_move_pct",
        "max_abs_move_pct",
        "url",
    ]
    with open(DATA / "lawsuit_moves.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
