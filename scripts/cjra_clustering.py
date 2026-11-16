"""Do federal judges rush bench-trial rulings out before the six-month-list cutoffs?

Under the Civil Justice Reform Act (CJRA), courts publicly report every bench trial and
motion a judge has held for more than six months, as of March 31 and September 30.
We count post-trial opinions ("trial opinion" or "findings of fact and conclusions of
law", excluding the parties' proposed findings) filed in each half-month of each year
in the free RECAP archive (CourtListener), then compare the two half-months before each
cutoff with the rest.

Output: data/cjra_halfmonth_counts.csv
"""

import calendar
import csv
import json
import urllib.parse

from common import DATA, get

CL = "https://www.courtlistener.com/api/rest/v4/search/"
TERMS = (
    'description:(("trial opinion" OR "findings of fact and conclusions of law") '
    "NOT proposed NOT notice NOT lodging NOT motion NOT brief NOT objection)"
)
YEARS = range(2016, 2026)


def count(lo: str, hi: str) -> int | None:
    q = f"{TERMS} AND entry_date_filed:[{lo}T00:00:00Z TO {hi}T23:59:59Z]"
    raw = get(CL + "?" + urllib.parse.urlencode({"type": "rd", "q": q}))
    try:
        return json.loads(raw)["count"]
    except (ValueError, KeyError):
        return None


def main() -> None:
    rows = []
    for y in YEARS:
        for m in range(1, 13):
            last = calendar.monthrange(y, m)[1]
            for half, (a, b) in enumerate([(1, 15), (16, last)]):
                n = count(f"{y}-{m:02d}-{a:02d}", f"{y}-{m:02d}-{b:02d}")
                cutoff = half == 1 and m in (3, 9)
                rows.append(
                    {
                        "year": y,
                        "month": m,
                        "half": half + 1,
                        "days": b - a + 1,
                        "rulings": n,
                        "before_cjra_cutoff": cutoff,
                    }
                )
                print(y, m, half + 1, n, "CUTOFF" if cutoff else "", flush=True)
    with open(DATA / "cjra_halfmonth_counts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["rulings"] is not None]
    cut = [r for r in ok if r["before_cjra_cutoff"]]
    per_day = lambda rs: sum(r["rulings"] for r in rs) / sum(r["days"] for r in rs)
    print(
        f"rulings/day before cutoffs {per_day(cut):.2f} vs other {per_day([r for r in ok if not r['before_cjra_cutoff']]):.2f}"
    )


if __name__ == "__main__":
    main()
