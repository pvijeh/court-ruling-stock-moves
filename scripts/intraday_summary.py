"""Summarize data/universe/combined/intraday_backtest.csv.

For each entry delay: trades, mean and median return per trade (against the benchmark),
hit rate, and the mean after an assumed cost per side. Split by case type, by company
size and by how big the move was, so one case (Pacira) can't carry the result alone.
Output: data/universe/combined/intraday_summary.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "universe" / "combined"
DELAYS = (0, 1, 2, 5, 15)
COSTS_BPS = (5, 25, 50)


def stats(d: pd.DataFrame, group: str, label: str) -> list[dict]:
    rows = []
    for k in DELAYS:
        x = d[f"trade_plus{k}"].dropna()
        if x.empty:
            continue
        rec = {
            "group": group,
            "value": label,
            "entry_minutes_after_post": k,
            "trades": len(x),
            "mean_ret": round(x.mean(), 4),
            "median_ret": round(x.median(), 4),
            "hit_rate": round((x > 0).mean(), 3),
            "t_stat": round(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))), 2)
            if len(x) > 2 and x.std(ddof=1) > 0
            else None,
            "mean_ret_without_best": round(x.drop(x.idxmax()).mean(), 4)
            if len(x) > 1
            else None,
            "sum_ret": round(x.sum(), 3),
        }
        for c in COSTS_BPS:
            rec[f"mean_after_{c}bps_per_side"] = round(x.mean() - 2 * c / 1e4, 4)
        rows.append(rec)
    return rows


def main() -> None:
    df = pd.read_csv(OUT / "intraday_backtest.csv")
    df = df[df["minute_bars"]]
    bins = [0, 1e9, 1e10, np.inf]
    df["size"] = (
        pd.cut(df["market_cap_usd_at_filing"], bins, labels=["<$1B", "$1-10B", ">$10B"])
        .cat.add_categories("unknown")
        .fillna("unknown")
    )
    df["move"] = pd.cut(
        df["abn_ret_decision_day"].abs(),
        [0, 0.02, 0.05, 0.10, np.inf],
        labels=["<2%", "2-5%", "5-10%", ">10%"],
        include_lowest=True,
    )
    rows = stats(df, "all", "all")
    for col in ("category", "size", "move"):
        for v, g in df.groupby(col, observed=True):
            rows += stats(g, col, str(v))
    s = pd.DataFrame(rows)
    s.to_csv(OUT / "intraday_summary.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(s.to_string(index=False))


if __name__ == "__main__":
    main()
