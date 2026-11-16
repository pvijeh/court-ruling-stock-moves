"""Combine the case-type universes into one table, rank case types for a fast alert,
and test how well the decision-day move can be predicted from facts known earlier.

Reads data/universe/<type>/cases.csv, writes data/universe/combined/*.csv.
Run: python3 scripts/combine_universe.py
"""

import glob
import os

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "universe", "combined")
# When the same stock and decision day appear in two case types, keep the first in this order.
PRIORITY = [
    "drug_patent",
    "merger_challenge",
    "deal_litigation",
    "antitrust_conduct",
    "jury_verdict",
    "itc337",
    "ptab",
]
NUM = [
    "market_cap_usd_at_filing",
    "revenue_at_stake_share",
    "abn_ret_filing_day",
    "ret_decision_day",
    "abn_ret_decision_day",
    "ret_decision_plus5",
    "adv_usd_20d_before_decision",
    "lead_minutes_vs_company_release",
    "minutes_to_half_move",
]
START = "2021-01-01"
TIMED = {"minute", "hour", "inferred from price"}
PARTY_KNOWS_FIRST = {"settled", "withdrawn"}


def load():
    frames = []
    for path in sorted(
        glob.glob(os.path.join(ROOT, "data", "universe", "*", "cases.csv"))
    ):
        cat = path.split(os.sep)[-2]
        if cat in PRIORITY:
            df = pd.read_csv(path, dtype=str).fillna("")
            df.insert(0, "category", cat)
            frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["decision_known_in_advance"] = df["decision_known_in_advance"].replace(
        "", "unknown"
    )
    df["during_market_hours"] = df["during_market_hours"].replace("", "unknown")
    df["outcome"] = df["outcome"].replace("", "unknown")
    df["abs_abn"] = df["abn_ret_decision_day"].abs()
    df["year"] = df["decision_date"].str[:4]
    df["rank"] = df["category"].map(PRIORITY.index)
    return df


def mark_events(df):
    """One event = one stock on one decision day. Several PTAB trials decided the same day
    for the same ticker share one price move, so moves are counted per event, not per row."""
    has = (df["ticker"] != "") & (df["decision_date"] != "")
    df["event_key"] = np.where(
        has, df["ticker"] + "|" + df["decision_date"], "row" + df.index.astype(str)
    )
    first_cat = df.sort_values("rank").groupby("event_key")["category"].first()
    df["dup_of_category"] = np.where(
        df["category"] != df["event_key"].map(first_cat),
        df["event_key"].map(first_cat),
        "",
    )
    return df


def one_per_event(d):
    """Keep one qualifying row per stock-day, from the highest-priority category."""
    return (
        d.sort_values("rank", kind="stable").drop_duplicates("event_key").sort_index()
    )


def priced_events(df):
    m = (
        df["abs_abn"].notna()
        & (df["decision_date"] >= START)
        & ~df["outcome"].isin(["pending", "unknown"])
    )
    return one_per_event(df[m])


def fast_alert(df):
    m = (
        (df["decision_known_in_advance"] == "no")
        & (df["during_market_hours"] == "yes")
        & df["time_precision"].isin(TIMED)
        & ~df["outcome"].isin(PARTY_KNOWS_FIRST)
        & (df["decision_date"] >= START)
    )
    return one_per_event(df[m])


def summarize(df):
    ev = priced_events(df)
    fa = fast_alert(df)
    rows = []
    for cat in PRIORITY:
        c = df[(df["category"] == cat) & (df["decision_date"] >= START)]
        e = ev[ev["category"] == cat]
        f = fa[fa["category"] == cat]
        fp = f[f["abs_abn"].notna()]
        big_u = e[
            (e["abs_abn"] > 0.10)
            & (e["decision_known_in_advance"] == "no")
            & ~e["outcome"].isin(PARTY_KNOWS_FIRST)
        ]
        tu = c[
            c["time_precision"].isin(TIMED)
            & (c["decision_known_in_advance"] == "no")
            & c["during_market_hours"].isin(["yes", "no"])
            & ~c["outcome"].isin(PARTY_KNOWS_FIRST)
        ]
        timed_n = len(tu)
        mh_share = (tu["during_market_hours"] == "yes").mean() if timed_n else np.nan
        span = (
            pd.to_datetime(e["decision_date"]).max()
            - pd.to_datetime(e["decision_date"]).min()
        ).days / 365.25
        rows.append(
            {
                "category": cat,
                "rows": len(c),
                "cases": c["case_id"].nunique(),
                "priced_events": len(e),
                "price_years": round(span, 1),
                "median_abs_abn": round(e["abs_abn"].median(), 4),
                "events_gt5": int((e["abs_abn"] > 0.05).sum()),
                "events_gt10": int((e["abs_abn"] > 0.10).sum()),
                "events_gt25": int((e["abs_abn"] > 0.25).sum()),
                "gt10_per_year": round((e["abs_abn"] > 0.10).sum() / span, 1)
                if span
                else None,
                "share_unscheduled": round(
                    (c["decision_known_in_advance"] == "no").mean(), 2
                ),
                "unscheduled_gt10_per_year": round(len(big_u) / span, 2)
                if span
                else None,
                "market_hours_share_of_timed": round(mh_share, 2) if timed_n else None,
                "n_timed_unscheduled": timed_n,
                "est_liquidia_like_per_year": round(len(big_u) / span * mh_share, 2)
                if span and timed_n
                else None,
                "share_timed": round(c["time_precision"].isin(TIMED).mean(), 2),
                "fast_alert_events": len(f),
                "fast_alert_priced": len(fp),
                "fast_alert_gt5": int((fp["abs_abn"] > 0.05).sum()),
                "fast_alert_gt10": int((fp["abs_abn"] > 0.10).sum()),
                "median_lead_min": f["lead_minutes_vs_company_release"].median(),
                "n_lead": int(f["lead_minutes_vs_company_release"].notna().sum()),
                "median_min_to_half": f["minutes_to_half_move"].median(),
                "n_half": int(f["minutes_to_half_move"].notna().sum()),
            }
        )
    return pd.DataFrame(rows)


def by_size(df):
    ev = priced_events(df).copy()
    bins = [0, 1e9, 1e10, np.inf]
    ev["size"] = pd.cut(
        ev["market_cap_usd_at_filing"], bins, labels=["<$1B", "$1-10B", ">$10B"]
    )
    ev["size"] = ev["size"].cat.add_categories("unknown").fillna("unknown")
    g = ev.groupby("size", observed=False)["abs_abn"]
    return pd.DataFrame(
        {
            "events": g.size(),
            "median_abs_abn": g.median().round(4),
            "share_gt10": g.apply(lambda s: round((s > 0.10).mean(), 3)),
        }
    ).reset_index()


def features(d, with_adv):
    x = pd.get_dummies(d["category"] + ":" + d["company_role"], dtype=float)
    mc = np.log10(
        d["market_cap_usd_at_filing"].where(d["market_cap_usd_at_filing"] > 0)
    )
    x["log_mcap"] = mc.fillna(0)
    x["mcap_missing"] = mc.isna().astype(float)
    rs = d["revenue_at_stake_share"].clip(0, 1)
    x["rev_share"] = rs.fillna(0)
    x["rev_share_missing"] = rs.isna().astype(float)
    x["scheduled"] = (d["decision_known_in_advance"] == "yes").astype(float)
    if with_adv:
        adv = np.log10(
            d["adv_usd_20d_before_decision"].where(d["adv_usd_20d_before_decision"] > 0)
        )
        x["log_adv"] = adv.fillna(0)
        x["adv_missing"] = adv.isna().astype(float)
    return x


def walk_forward(df, exclude_ptab):
    """Train on decisions before year Y, test on year Y. Target: size of the abnormal move."""
    ev = priced_events(df)
    if exclude_ptab:
        ev = ev[ev["category"] != "ptab"]
    out = []
    for setting, with_adv in [("at_filing", False), ("before_decision", True)]:
        x_all = features(ev, with_adv)
        y = ev["abs_abn"].values
        preds = {"category_median": [], "ridge": [], "boosted_trees": []}
        baseline = []
        actual, years = [], []
        for yr in ["2023", "2024", "2025", "2026"]:
            tr, te = (ev["year"] < yr).values, (ev["year"] == yr).values
            if tr.sum() < 50 or te.sum() < 10:
                continue
            baseline += [np.median(y[tr])] * int(te.sum())
            med = ev[tr].groupby("category")["abs_abn"].median()
            preds["category_median"] += list(
                ev[te]["category"].map(med).fillna(np.median(y[tr]))
            )
            preds["ridge"] += list(
                Ridge(alpha=1.0).fit(x_all[tr], y[tr]).predict(x_all[te])
            )
            gbr = GradientBoostingRegressor(
                loss="absolute_error",
                n_estimators=200,
                max_depth=3,
                learning_rate=0.05,
                random_state=0,
            )
            preds["boosted_trees"] += list(gbr.fit(x_all[tr], y[tr]).predict(x_all[te]))
            actual += list(y[te])
            years.append(yr)
        a = np.array(actual)
        big = a > 0.10
        n_top = round(0.1 * len(a))
        for name, p in preds.items():
            p = np.array(p)
            # exactly the top 10%; ties broken at random with a fixed seed
            order = np.random.default_rng(0).permutation(len(p))
            top = np.zeros(len(p), dtype=bool)
            top[order[np.argsort(-p[order], kind="stable")[:n_top]]] = True
            out.append(
                {
                    "sample": "excluding_ptab" if exclude_ptab else "all",
                    "features": setting,
                    "model": name,
                    "test_years": ",".join(years),
                    "n_test": len(a),
                    "mae": round(np.mean(np.abs(p - a)), 4),
                    "mae_predict_training_median": round(
                        np.mean(np.abs(np.array(baseline) - a)), 4
                    ),
                    "spearman": round(spearmanr(p, a).statistic, 3),
                    "big_move_base_rate": round(big.mean(), 3),
                    "big_move_rate_in_top_decile": round(big[top].mean(), 3),
                    "share_of_big_moves_in_top_decile": round(
                        big[top].sum() / max(big.sum(), 1), 3
                    ),
                }
            )
    return pd.DataFrame(out)


def main():
    df = mark_events(load())
    os.makedirs(OUT, exist_ok=True)
    df.drop(columns=["rank"]).to_csv(os.path.join(OUT, "cases.csv"), index=False)
    s = summarize(df)
    s.to_csv(os.path.join(OUT, "summary_by_category.csv"), index=False)
    fa = fast_alert(df)
    cols = [
        "category",
        "case_name",
        "ticker",
        "company_role",
        "outcome",
        "decision_date",
        "first_public_source",
        "first_public_time_et",
        "time_precision",
        "abn_ret_decision_day",
        "market_cap_usd_at_filing",
        "lead_minutes_vs_company_release",
        "minutes_to_half_move",
        "confidence",
    ]
    fa.sort_values("abs_abn", ascending=False)[cols].to_csv(
        os.path.join(OUT, "fast_alert_events.csv"), index=False
    )
    sz = by_size(df)
    sz.to_csv(os.path.join(OUT, "moves_by_company_size.csv"), index=False)
    wf = pd.concat([walk_forward(df, False), walk_forward(df, True)])
    wf.to_csv(os.path.join(OUT, "prediction_walkforward.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(
        "rows",
        len(df),
        "duplicate-event rows",
        int((df["dup_of_category"] != "").sum()),
    )
    print(s.T.to_string())
    print(sz.to_string())
    print(
        fa[fa["abs_abn"] > 0.05]
        .sort_values("abs_abn", ascending=False)[cols[:6] + cols[7:13]]
        .to_string()
    )
    print(wf.to_string())


if __name__ == "__main__":
    main()
