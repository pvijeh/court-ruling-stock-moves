"""Check PTAB final-decision labels against the decision posted on the decision day.

The universe build took the outcome from the original final written decision even when
the case ended later with a decision on remand (e.g. IPR2021-00455: the 2022 decision
upheld Universal Electronics' claims, the 2025 remand decision cancelled all of them).

For every PTAB final-decision row in data/universe/combined/cases.csv that is either in
the intraday window (decided on or after EARLIEST, during market hours) or decided more
than 200 days after its statutory deadline (a sign of a remand), this script:

- downloads the case's document list from P-TACTS and picks the final decision posted
  within 3 days of the decision date,
- reads the outcome twice from that PDF: the caption/first-page reading the build uses,
  and separately the ORDER paragraph on the last pages,
- relabels the row when both readings agree and differ from the old label; rows where
  the readings disagree or can't be read are listed for a hand check.

Writes data/universe/ptab/label_audit.csv and updates outcome, outcome_for_company and
notes in data/universe/combined/cases.csv and data/universe/ptab/cases.csv.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import universe_ptab as up
from intraday_backtest import EARLIEST

ROOT = Path(__file__).resolve().parents[1]
COMBINED = ROOT / "data" / "universe" / "combined" / "cases.csv"
PTAB = ROOT / "data" / "universe" / "ptab" / "cases.csv"
AUDIT = ROOT / "data" / "universe" / "ptab" / "label_audit.csv"
LATE_DAYS = 200


def order_result(text: str) -> str:
    """'all' / 'some' / 'none' from the ORDER paragraph only ('' if not found)."""
    t = re.sub(r"\s+", " ", text)
    i = t.rfind("ORDERED")
    if i < 0:
        return ""
    o = t[max(0, i - 50) : i + 1500]
    shown = up.ORDER_SHOWN.search(o) or re.search(r"(are|is) unpatentable", o)
    not_shown = up.ORDER_NOT.search(o) or re.search(
        r"not (been )?shown|not established|not unpatentable", o
    )
    if shown and not_shown:
        return "some"
    return "all" if shown else "none" if not_shown else ""


def candidates(c: pd.DataFrame) -> pd.DataFrame:
    f = c[
        (c["category"] == "ptab") & c["notes"].str.startswith("final written decision")
    ]
    dl = pd.to_datetime(
        f["notes"].str.extract(
            r"statutory deadline for the final decision (\d{4}-\d\d-\d\d)"
        )[0]
    )
    late = (pd.to_datetime(f["decision_date"]) - dl).dt.days
    window = (f["decision_date"] >= str(EARLIEST)) & (f["during_market_hours"] == "yes")
    return f[window | (late > LATE_DAYS) | dl.isna()]


def main() -> None:
    c = pd.read_csv(COMBINED, dtype=str).fillna("")
    cand = candidates(c)
    ids = sorted(cand["case_id"].unique())
    print(f"{len(cand)} rows, {len(ids)} cases to check", flush=True)
    res = {}
    for i, num in enumerate(ids):
        day = pd.to_datetime(
            cand.loc[cand["case_id"] == num, "decision_date"].iloc[0]
        ).date()
        arts = up.fetch_json(
            f"{up.PTACTS}/proceeding-artifacts?proceedingNumber={num}",
            "artifacts",
            key=num,
        )
        docs = [
            a
            for a in up.final_docs(arts if isinstance(arts, list) else [])
            if a.get("artifactIdentifer")
        ]
        doc = up.final_doc_near(docs, day)
        rec = {"case_id": num, "decision_date": str(day), "final_docs": len(docs)}
        if doc:
            text = up.fwd_text(doc)
            rec.update(
                doc_posted_et=f"{up.et(doc['filingDate']):%Y-%m-%d %H:%M}",
                doc_type=doc.get("documentTypeCode") or "",
                doc_name=re.sub(r"\s+", " ", doc.get("name") or "")[:120],
                remand="remand" in (doc.get("name") or "").lower()
                or doc.get("documentTypeCode") == "FINAL:RMD",
                caption_result=up.fwd_result_pdf(text) if text else "",
                order_result=order_result(text) if text else "",
                doc_url=up.doc_url(doc),
            )
        res[num] = rec
        if i % 25 == 0:
            print(f"  {i}/{len(ids)}", flush=True)

    rows = []
    for idx, r in cand.iterrows():
        a = res[r["case_id"]]
        cap, order = a.get("caption_result", ""), a.get("order_result", "")
        new = up.OUTCOME.get(("fwd", cap, r["company_role"]), "")
        chk = up.OUTCOME.get(("fwd", order, r["company_role"]), "")
        # the caption ("Determining All/No/Some Challenged Claims Unpatentable") is the
        # Board's own summary; the ORDER paragraph is only a cross-check
        status = (
            "no decision found"
            if "doc_url" not in a
            else "unreadable"
            if not new
            else "agree"
            if new == r["outcome"]
            else "relabel"
            if chk in ("", new)
            else "hand check"
        )
        rows.append(
            {
                **a,
                "row": idx,
                "ticker": r["ticker"],
                "company_role": r["company_role"],
                "old_outcome": r["outcome"],
                "caption_outcome": new,
                "order_outcome": chk,
                "status": status,
            }
        )
    out = pd.DataFrame(rows)
    out.drop(columns="row").to_csv(AUDIT, index=False)
    print(out["status"].value_counts().to_string())

    fix = out[out["status"] == "relabel"]
    p = pd.read_csv(PTAB, dtype=str).fillna("")
    for _, f in fix.iterrows():
        note = (
            f"; outcome relabelled from the decision posted {f['doc_posted_et']} "
            f"({f['doc_name']}): was {f['old_outcome']}"
        )
        for df, m in (
            (c, c.index == f["row"]),
            (p, (p["case_id"] == f["case_id"]) & (p["ticker"] == f["ticker"])),
        ):
            df.loc[m, "outcome"] = f["caption_outcome"]
            df.loc[m, "outcome_for_company"] = up.FOR_CO.get(
                f["caption_outcome"], "unknown"
            )
            df.loc[m, "decision_source_url"] = f["doc_url"]
            df.loc[m, "notes"] = df.loc[m, "notes"] + note
    c.to_csv(COMBINED, index=False)
    p.to_csv(PTAB, index=False)
    print(f"relabelled {len(fix)} rows")
    print(
        fix[
            [
                "case_id",
                "ticker",
                "decision_date",
                "old_outcome",
                "caption_outcome",
                "remand",
            ]
        ].to_string()
    )


if __name__ == "__main__":
    main()
