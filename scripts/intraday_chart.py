"""Chart: average return per trade by entry delay, per case type (from intraday_summary.csv)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe" / "combined"


def main() -> None:
    s = pd.read_csv(OUT / "intraday_summary.csv")
    d = s[
        s["group"].isin(["all", "category"])
        | ((s["group"] == "move") & (s["value"] == ">10%"))
    ]
    d = d[d.groupby("value")["trades"].transform("max") >= 5].copy()
    d.loc[d["value"] == ">10%", "value"] = "rulings that moved the stock >10% that day"
    d["label"] = (
        d["value"]
        + " (n="
        + d.groupby("value")["trades"].transform("max").astype(str)
        + ")"
    )
    d["mean_pct"] = d["mean_ret"] * 100
    sns.set_theme(style="whitegrid", palette="colorblind")
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.lineplot(
        data=d,
        x="entry_minutes_after_post",
        y="mean_pct",
        hue="label",
        marker="o",
        ax=ax,
    )
    ax.axhline(0, color="black", lw=0.8)
    ax.axhline(
        0.1, color="grey", ls="--", lw=0.8, label="cost of round trip at 5 bps a side"
    )
    ax.set_xlabel("Minutes after the ruling was posted when the trade is entered")
    ax.set_ylabel("Average return per trade vs. benchmark, to the close (%)")
    ax.set_title("Trading the ruling from the minute it was posted made about nothing")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = ROOT / "docs" / "img" / "intraday_backtest.png"
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=150)
    print(path)


if __name__ == "__main__":
    main()
