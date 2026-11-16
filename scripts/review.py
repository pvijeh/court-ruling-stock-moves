"""Hand review of the automatic matches in data/lawsuit_moves.csv.

The automatic pick is the court document near the ruling date with the biggest
stock move, so it sometimes lands on a motion or stipulation instead of the
ruling. Each candidate gets a status after reading the matched docket entry:

- ok: the matched entry is the ruling (or the order issued with it)
- needs_check: probably the ruling, but the docket text was empty
- wrong_document: the matched entry is not the ruling; the move is not usable
- no_match: no ruling found on CourtListener near the given date

Output: data/lawsuit_moves_reviewed.csv
"""

import csv
import re

from common import DATA

OK, CHECK, WRONG, NONE = "ok", "needs_check", "wrong_document", "no_match"

REVIEW = {
    "YUTREPIA '327 trial opinion": (
        OK,
        "D.I. 475 opinion; D.I. 474 order rejecting the invalidity defense came at 11:15",
        None,
    ),
    "search antitrust remedies": (
        OK,
        "matched the redactions order (ECF 1437); the opinion ECF 1436 was filed at 16:05",
        "2025-09-02T16:05:00-04:00",
    ),
    "search antitrust liability": (
        OK,
        "redactions order for opinion ECF 1033; Aug 5 2024 was also a market-wide sell-off",
        None,
    ),
    "ad tech liability": (OK, "", None),
    "Tapestry-Capri merger blocked": (OK, "", None),
    "Kroger-Albertsons blocked": (OK, "", None),
    "JetBlue-Spirit blocked": (NONE, "", None),
    "FTC v Meta monopoly ruling": (OK, "", None),
    "Epic v Apple contempt order": (WRONG, "matched a statement, not the order", None),
    "Korlym patent trial": (
        OK,
        "date only; check the next trading day (Jan 2 2024)",
        None,
    ),
    "Lumryz injunction": (NONE, "", None),
    "Eylea biosimilar injunction denied": (OK, "sealed order", None),
    "Eylea biosimilar injunction": (WRONG, "matched a motion", None),
    "jury verdict $445M": (WRONG, "matched a motion; verdict came later", None),
    "jury verdict $118M": (WRONG, "matched a motion", None),
    "jury verdict $634M": (WRONG, "matched a notice of lodging", None),
    "talc bankruptcy dismissed": (WRONG, "matched a transcript order", None),
    "Cabometyx patent ruling": (OK, "final judgment before the open", None),
    "Exparel patent ruling": (
        OK,
        "order asking for a proposed judgment, issued with the opinion",
        None,
    ),
    "Entresto trial opinion": (CHECK, "docket text empty", None),
    "Pluvicto/Lutathera opinion": (OK, "date only", None),
    "Vertex patent opinion": (OK, "date only", None),
    "Calquence patent opinion": (OK, "", None),
    "Nuplazid patent opinion": (OK, "date only", None),
    "INOmax patent opinion": (NONE, "", None),
    "Pfizer patent opinion": (
        OK,
        "order issued with the opinion, before the open",
        None,
    ),
    "Novo patent opinion": (OK, "date only", None),
    "RaDaR preliminary injunction": (OK, "after the close", None),
    "false-advertising verdict $292M": (WRONG, "matched a sealing motion", None),
    "LNP patent claim construction": (WRONG, "matched a sealing motion", None),
    "Vanda v FDA rulings": (WRONG, "matched a brief", None),
    "Wakix patent opinion": (WRONG, "matched a stipulation", None),
    "Supernus patent opinion": (NONE, "", None),
    "inhaler Orange Book case": (NONE, "", None),
    "Vascepa induced infringement": (
        WRONG,
        "matched a settlement-enforcement order",
        None,
    ),
    "Xifaxan patent": (WRONG, "matched an appeals-court docketing order", None),
    "Incyte patent opinion": (NONE, "", None),
    "Halozyme patent case": (NONE, "", None),
    "Sage patent case": (WRONG, "matched a stipulation", None),
    "Cytokinetics case": (NONE, "", None),
}


def case_name(url: str) -> str:
    m = re.search(r"/docket/\d+/[^/]+/(?:\d+/)?([a-z0-9-]+)/?$", url or "")
    return m.group(1).replace("-", " ") if m else ""


def main() -> None:
    with open(DATA / "lawsuit_moves.csv") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        status, note, fixed_time = REVIEW[r["note"]]
        r["case"] = r.get("case") or case_name(r.get("url", ""))
        r["review_status"] = status
        r["review_note"] = note
        if fixed_time:
            r["filed_et"] = fixed_time
    fields = list(rows[0]) + [
        k for k in ("review_status", "review_note") if k not in rows[0]
    ]
    with open(DATA / "lawsuit_moves_reviewed.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    for s in (OK, CHECK, WRONG, NONE):
        print(s, sum(r["review_status"] == s for r in rows))


if __name__ == "__main__":
    main()
