"""Docket minute for court rulings that only had a date, then the Liquidia check.

For every non-PTAB ruling in the minute-price window (data/universe/combined/cases.csv):
- find the case's CourtListener docket (from docket_url, or court + docket number)
- take the earliest docket entry on the decision day that reads like the ruling (opinion,
  findings, judgment, order on infringement or validity), with CM/ECF's filing time
- skip entries posted under seal: the outcome was not public at that minute

Then, for rulings with a minute during market hours, the same volume test as
posting_time_check.py and the same trade as intraday_backtest.py (enter 1 minute after
the docket time, exit at the close, minus XBI for drug patents or SPY otherwise).

Rows the docket can't time (ITC, Federal Circuit, state courts, juries, agencies) are
listed with the reason. Needs COURTLISTENER_API_TOKEN and POLYGON_API_KEY.
Output: data/universe/combined/court_minute_times.csv
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests

import intraday_backtest as ib
import intraday_strict as st
import posting_time_check as pc

CL = "https://www.courtlistener.com/api/rest/v4"
CACHE = Path.home() / "work" / "altdata" / "cache" / "courtlistener"
COURTS = {
    "ded": "ded", "njd": "njd", "D. Del.": "ded", "D.N.J.": "njd", "D. Or.": "ord",
    "S.D.N.Y.": "nysd", "N.D. Cal.": "cand", "E.D. Va.": "vaed", "D.D.C.": "dcd",
    "N.D. Ill.": "ilnd", "S.D. Tex.": "txsd", "S.D. W.Va.": "wvsd", "D. Md.": "mdd",
    "E.D. Tex.": "txed", "W.D. Tex.": "txwd", "D. Colo.": "cod", "W.D. Wash.": "wawd",
    "C.D. Cal.": "cacd", "E.D. Cal.": "caed", "M.D.N.C.": "ncmd", "W.D. Ark.": "arwd",
    "D. Mass.": "mad", "S.D. Fla.": "flsd",
}  # fmt: skip
RULING = re.compile(
    r"(?i)opinion|findings of fact|judgment|verdict|memorandum order"
    r"|^ORDER\b.*\b(infring\w*|(in)?valid\w*|injunction|enjoin\w*|dismiss\w*)\b"
)
# CM/ECF filing times are in the court's local time
COURT_TZ = {
    "ord": "America/Los_Angeles", "cand": "America/Los_Angeles", "cacd": "America/Los_Angeles",
    "caed": "America/Los_Angeles", "wawd": "America/Los_Angeles", "cod": "America/Denver",
    "ilnd": "America/Chicago", "txsd": "America/Chicago", "txed": "America/Chicago",
    "txwd": "America/Chicago", "arwd": "America/Chicago", "mnd": "America/Chicago",
}  # fmt: skip
# party filings that mention a ruling (proposed verdict forms, stipulations, motions)
NOT_RULING = re.compile(
    r"(?i)^ORDER directing [^.]*submit|notice of appeal|transcript"
    r"|\bproposed\W+(\w+ ){0,2}(verdict|order|findings|judgment|form)\b|^verdict sheet by"
    r"|^\W*(proposed|joint|stipulat\w*|motion|letter|brief|response|reply|objection"
    r"|notice|declaration|memorandum (of law|in support))\b"
)
# "[UNSEALED on <date>]" marks an entry filed under seal and opened later; a new entry
# "OPINION - Unsealed ..." is the public version, posted at its own time
SEALED = re.compile(r"(?i)\bsealed\b|under seal|\[unsealed on ")
# the API token allows 50 calls an hour
GAP = float(os.environ.get("COURTLISTENER_GAP", "75"))
_last = 0.0


def cl(path: str, **params) -> dict:
    global _last
    key = re.sub(
        r"[^\w.-]", "_", path + "_" + "_".join(f"{k}-{v}" for k, v in params.items())
    )
    p = CACHE / f"{key}.json.gz"
    if p.exists():
        return json.loads(gzip.decompress(p.read_bytes()))
    p.parent.mkdir(parents=True, exist_ok=True)
    head = {"Authorization": f"Token {os.environ['COURTLISTENER_API_TOKEN']}"}
    for _ in range(12):
        time.sleep(max(0.0, _last + GAP - time.time()))
        _last = time.time()
        try:
            r = requests.get(f"{CL}/{path}/", params=params, headers=head, timeout=60)
        except requests.RequestException as e:
            r = e
            continue
        if r.status_code == 200:
            p.write_bytes(gzip.compress(r.content))
            return r.json()
        # rate limited: wait as told, unless it's the daily cap (125/day)
        wait = float(r.headers.get("Retry-After") or 60)
        if wait > 3600:
            raise RuntimeError(
                f"CourtListener limit, available again in {wait / 3600:.0f} h"
            )
        time.sleep(wait)
    raise RuntimeError(
        f"CourtListener {path} {params} -> {getattr(r, 'status_code', r)}"
    )


def docket_ids(r: pd.Series) -> tuple[list[int], str]:
    m = re.search(r"courtlistener\.com/docket/(\d+)", r["docket_url"])
    if m:
        return [int(m.group(1))], ""
    if r["court"] == "cafc":
        return [], "Federal Circuit opinion: no posting time on the docket"
    court = COURTS.get(r["court"].strip())
    if not court:
        return [], f"no docket source for court '{r['court'] or r['category']}'"
    # a GovInfo link names the lead case; otherwise try the first few listed dockets
    lead = re.findall(r"USCOURTS-\w+-\d_(\d{2})-cv-(\d{1,5})", r["docket_url"])
    nums = (
        lead or re.findall(r"(?:\d:)?(\d{2})-(?:cv-)?(\d{1,5})", r["docket_number"])[:4]
    )
    if not nums:
        return [], "no docket number in our data"
    ids = []
    for num in nums:
        core = f"{num[0]}{int(num[1]):05d}"
        res = cl("dockets", court=court, docket_number_core=core).get("results") or []
        ids += [d["id"] for d in res]
    return ids, "" if ids else "docket not on CourtListener"


def court_of(docket: int) -> str:
    """CourtListener court id of a docket (from the cached docket lookups, else the API)."""
    for p in CACHE.glob("dockets_court-*.json.gz"):
        for d in json.loads(gzip.decompress(p.read_bytes())).get("results") or []:
            if d["id"] == docket:
                return p.name.split("court-")[1].split("_")[0]
    return cl(f"dockets/{docket}").get("court_id", "")


def ruling_entry(ids: list[int], day: str) -> tuple[str, str, str]:
    """(time 'YYYY-MM-DD HH:MM', entry description, reason if none)."""
    best, why = ("", ""), "no ruling entry on the decision day"
    for d in ids:
        res = cl("docket-entries", docket=d, date_filed__gte=day, date_filed__lte=day)
        for e in res.get("results") or []:
            desc = e.get("description") or " ".join(
                x.get("description") or "" for x in e.get("recap_documents") or []
            )
            if not RULING.search(desc) or NOT_RULING.search(desc):
                continue
            if SEALED.search(desc):
                why = "ruling entry posted under seal or unsealed later"
                continue
            if not e.get("time_filed"):
                why = "ruling entry has no filing time"
                continue
            tz = COURT_TZ.get(court_of(d), "America/New_York")
            t = (
                pd.Timestamp(f"{day} {e['time_filed']}", tz=tz)
                .tz_convert(ib.ET)
                .strftime("%Y-%m-%d %H:%M")
            )
            if not best[0] or t < best[0]:
                best = (t, desc[:140])
    return best[0], best[1], "" if best[0] else why


def main() -> None:
    c = pd.read_csv(ib.OUT / "cases.csv", dtype=str).fillna("")
    c = c[
        (c["category"] != "ptab")
        & (c["decision_date"] >= str(ib.EARLIEST))
        & (c["ticker"] != "")
        & (c["dup_of_category"] == "")
        & ~c["outcome"].isin(["settled", "withdrawn"])
    ]
    # biggest movers first, saved after each row (the rate limit makes a full run slow)
    c = c.assign(_abs=pd.to_numeric(c["abn_ret_decision_day"], errors="coerce").abs())
    c = c.sort_values("_abs", ascending=False)
    rows = []
    for _, r in c.iterrows():
        try:
            ids, why = docket_ids(r)
            t, desc, why2 = (
                ruling_entry(ids, r["decision_date"]) if ids else ("", "", why)
            )
        except RuntimeError as e:
            # cached rows rerun instantly, so rerunning later picks up where this stopped
            print(f"stopped after {len(rows)} of {len(c)} rows: {e}")
            break
        out = {
            **{k: r[k] for k in ("case_id", "event_key", "category", "ticker", "company",
                                 "decision_date", "outcome", "outcome_for_company",
                                 "decision_known_in_advance", "abn_ret_decision_day",
                                 "time_precision", "first_public_time_et")},
            "docket_minute": t, "docket_entry": desc, "untimed_reason": why2,
        }  # fmt: skip
        if t and "09:30" <= t[11:] < "15:58":
            bench = "XBI" if r["category"] == "drug_patent" else "SPY"
            q = pd.Series({**out, "benchmark": bench, "posted_et": t})
            out.update(pc.check(q))
            day = pd.to_datetime(r["decision_date"]).date()
            t0 = pd.Timestamp(t).tz_localize(ib.ET)
            s, b = st.cached_day(r["ticker"], day), st.cached_day(bench, day)
            sr, br = ib.window_ret(s, t0, 1), ib.window_ret(b, t0, 1)
            sign = {"good": 1, "bad": -1}.get(r["outcome_for_company"], 0)
            if sr is not None and br is not None and sign:
                out["trade_plus1"] = sign * (sr - br)
        rows.append(out)
        df = pd.DataFrame(rows)
        df.to_csv(ib.OUT / "court_minute_times.csv", index=False)
    timed = df[df["docket_minute"] != ""]
    print(
        f"{len(df)} non-PTAB rulings in the window; {len(timed)} timed from the docket"
    )
    print(
        df.loc[df["docket_minute"] == "", "untimed_reason"].value_counts().to_string()
    )


if __name__ == "__main__":
    main()
