"""Did the stock react at the posting minute we trade on, or earlier?

For each stock-day in intraday_backtest.csv, using the cached minute bars:
- vol_ratio_at_post: largest volume in the posting minute and the 2 after it, over the
  day's median minute volume
- peak_minute_offset: minutes from posting to the day's highest-volume minute
- first_spike_offset: minutes from posting to the first minute with 10x median volume
(volume counted 9:40 to 15:50 only; the median is over the quiet minutes before posting)
- share_before: share of the open-to-close abnormal move that happened before posting

A posting time that is the real first public moment should show the spike at offset 0 to 2
(as Liquidia did on 2026-09-30: 318,713 shares in the filing minute against a 1,537 median).
A spike well before posting means someone had the news earlier.

Output: data/universe/combined/posting_time_check.csv and a summary.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import intraday_backtest as ib
import intraday_strict as st

SPIKE = 10
QUIET = (pd.Timestamp("09:40").time(), pd.Timestamp("15:50").time())


def check(r: pd.Series) -> dict:
    day = pd.to_datetime(r["decision_date"]).date()
    t0 = pd.Timestamp(r["posted_et"]).tz_localize(ib.ET)
    s, b = st.cached_day(r["ticker"], day), st.cached_day(r["benchmark"], day)
    if len(s) < 30 or len(b) < 30:
        return {}
    off = ((s.index - t0) / pd.Timedelta(minutes=1)).astype(int)
    # skip the opening and closing auctions, which are always heavy
    mid = (s.index.time >= QUIET[0]) & (s.index.time < QUIET[1])
    # baseline: quiet minutes before posting (the whole day if posted early)
    base = s[mid & (off < -5)]
    if len(base) < 15:
        base = s[mid & ((off < -5) | (off > 15))]
    med = max(float(base["v"].median()), 1.0) if len(base) else 1.0
    at = s[(off >= 0) & (off <= 2)]
    spikes = off[mid & (s["v"].to_numpy() >= SPIKE * med)]
    v = s["v"].where(mid, 0).to_numpy()
    pre_s = s[s.index < t0]
    pre_b = b[b.index < t0]
    total = (s["c"].iloc[-1] / s["o"].iloc[0]) - (b["c"].iloc[-1] / b["o"].iloc[0])
    pre = (
        (pre_s["c"].iloc[-1] / s["o"].iloc[0]) - (pre_b["c"].iloc[-1] / b["o"].iloc[0])
        if len(pre_s) and len(pre_b)
        else 0.0
    )
    return {
        "median_min_vol": med,
        "vol_ratio_at_post": float(at["v"].max() / med) if len(at) else np.nan,
        "peak_minute_offset": int(off[v.argmax()]),
        "chance_spike_3min": 1 - (1 - (base["v"] >= SPIKE * med).mean()) ** 3,
        "first_spike_offset": int(spikes.min()) if len(spikes) else np.nan,
        "abn_open_to_close": total,
        "share_before": pre / total if abs(total) > 0.005 else np.nan,
    }


def label(x: pd.Series) -> str:
    if pd.isna(x.get("vol_ratio_at_post")):
        return "no bars"
    if x["vol_ratio_at_post"] >= SPIKE:
        return "spike at posting"
    if x["first_spike_offset"] < -2:
        return "spike before posting"
    if x["first_spike_offset"] > 2:
        return "spike after posting only"
    return "no spike"


def main() -> None:
    ev = pd.read_csv(ib.OUT / "intraday_backtest.csv")
    # calibration: Liquidia's district-court loss, timed by hand from the docket
    lqda = {"ticker": "LQDA", "benchmark": "XBI", "decision_date": "2026-09-30"}
    print(
        "Liquidia 2026-09-30 11:15:",
        check(pd.Series({**lqda, "posted_et": "2026-09-30 11:15"})),
    )
    rows = [{**r.to_dict(), **check(r)} for _, r in ev.iterrows()]
    out = pd.DataFrame(rows)
    out["timing"] = out.apply(label, axis=1)
    out["abs_move"] = out["abn_open_to_close"].abs()
    out.to_csv(ib.OUT / "posting_time_check.csv", index=False)
    for name, g in (
        ("all stock-days", out),
        ("moved 5%+ open to close", out[out["abs_move"] >= 0.05]),
    ):
        print(f"{name}: {len(g)}")
        print(g["timing"].value_counts().to_string())
        print(
            f"  median share of the move before posting: {g['share_before'].median():.0%}; "
            f"chance of a {SPIKE}x minute in any 3-minute window: "
            f"{g['chance_spike_3min'].mean():.1%}"
        )


if __name__ == "__main__":
    main()
