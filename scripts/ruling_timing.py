"""Could each ruling's timing have been estimated from the public docket?

For each reviewed ruling in data/lawsuit_moves_reviewed.csv, find the last post-trial or final-argument
filing on the same docket before the ruling (post-trial briefs, proposed findings,
closing arguments, final hearing). Record days from that filing to the ruling, and
whether the ruling fell in the 14 days before a March 31 or September 30 cutoff for
the courts' public "six-month list" (Civil Justice Reform Act).

Output: data/ruling_timing.csv
"""

import csv
import json
import re
import urllib.parse
from datetime import date, timedelta

from common import DATA, get

CL = "https://www.courtlistener.com/api/rest/v4/search/"
LAST_STEP = (
    'description:("post-trial" OR "posttrial" OR "proposed findings" OR '
    '"closing argument" OR "oral argument" OR "bench trial" OR "jury trial" OR '
    '"evidentiary hearing")'
)

# transcripts, notices and scheduling entries mention a hearing without being one
NOT_STEP = (
    "-description:(transcript OR notice OR redacted OR redaction OR scheduling "
    "OR stipulation OR extension)"
)


def near_cutoff(d: date) -> bool:
    for c in (date(d.year, 3, 31), date(d.year, 9, 30)):
        if timedelta(0) <= c - d <= timedelta(days=14):
            return True
    return False


def last_step(docket_id: str, ruled: date) -> dict | None:
    lo = ruled - timedelta(days=4 * 365)
    hi = ruled - timedelta(days=1)
    q = (
        f"docket_id:{docket_id} AND {LAST_STEP} AND {NOT_STEP} AND "
        f"entry_date_filed:[{lo}T00:00:00Z TO {hi}T23:59:59Z]"
    )
    params = {"type": "rd", "q": q, "order_by": "entry_date_filed desc"}
    try:
        res = json.loads(get(CL + "?" + urllib.parse.urlencode(params)))["results"]
    except (ValueError, KeyError):
        return None
    return res[0] if res else None


def main() -> None:
    rows = []
    with open(DATA / "lawsuit_moves_reviewed.csv") as f:
        moves = list(csv.DictReader(f))
    for r in moves:
        if r["review_status"] not in ("ok", "needs_check"):
            continue
        ruled = date.fromisoformat(r["filed_et"][:10])
        m = re.search(r"/docket/(\d+)/", r.get("url", ""))
        e = last_step(m.group(1), ruled) if m else None
        prev = date.fromisoformat(str(e["entry_date_filed"])[:10]) if e else None
        rows.append(
            {
                "tickers": r["tickers"],
                "note": r["note"],
                "ruled": ruled.isoformat(),
                "last_step_date": prev.isoformat() if prev else "",
                "last_step_document": (e or {}).get("document_number") or "",
                "last_step": ((e or {}).get("description") or "")[:140],
                "days_last_step_to_ruling": (ruled - prev).days if prev else "",
                "within_14d_before_cjra_cutoff": near_cutoff(ruled),
            }
        )
        print(
            rows[-1]["tickers"],
            ruled,
            prev,
            rows[-1]["within_14d_before_cjra_cutoff"],
            flush=True,
        )
    with open(DATA / "ruling_timing.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
