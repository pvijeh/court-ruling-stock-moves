"""What LQDA and UTHR option prices implied about the Sept 30, 2026 ruling.

Reads stock_daily.csv and option_daily.csv (from fetch_options.py) and writes
implied_by_day.csv plus two charts.

For each trading day and each option expiry we compute:
- atm_iv: implied volatility of options struck near the stock price.
- implied_move_pct: the price of an at-the-money straddle (one call plus one
  put at the stock price) as a percent of the stock, using atm_iv.
- straddle_traded_pct: the same from real trades, when a call and a put at the
  strike nearest the stock both traded that day.
- q_put: a simple ceiling on the priced odds of "stock ends near the loss
  price before expiry": put price / (strike - loss price).
- q_mix, sigma_mix: a two-outcome fit. The stock either jumps to the loss price
  (odds q) or to a win price set so the average equals today's forward price,
  with ordinary day-to-day noise (sigma) on top of either outcome.

Only contracts that traded that day (volume > 0) are used. Yahoo's daily close
for an option is its last trade, which can be hours older than the stock close.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize, minimize_scalar
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
RATE = 0.04  # rough short-term US rate; changes results very little
RULING = date(2026, 9, 30)
LOSS = {"LQDA": 30.26}  # LQDA close on ruling day
UTHR_JUMP = 0.125  # UTHR gain on ruling day
GREEN, GREY, RED = "#3d7a5a", "#9a9a9a", "#b0413e"


def black(fwd: float, k: float, t: float, vol: float, kind: str) -> float:
    """Black-76 option price on a forward, discounted at RATE."""
    disc = math.exp(-RATE * t)
    if vol <= 0 or t <= 0:
        return disc * max(0.0, (fwd - k) if kind == "C" else (k - fwd))
    sd = vol * math.sqrt(t)
    d1 = (math.log(fwd / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    if kind == "C":
        return disc * (fwd * norm.cdf(d1) - k * norm.cdf(d2))
    return disc * (k * norm.cdf(-d2) - fwd * norm.cdf(-d1))


def implied_vol(price: float, fwd: float, k: float, t: float, kind: str) -> float:
    lo, hi = black(fwd, k, t, 1e-4, kind), black(fwd, k, t, 6.0, kind)
    if not lo < price < hi:
        return float("nan")
    return brentq(lambda v: black(fwd, k, t, v, kind) - price, 1e-4, 6.0)


def mixture_price(fwd, k, t, sigma, q, low, kind):
    high = max((fwd - q * low) / (1 - q), 1e-6)
    return q * black(low, k, t, sigma, kind) + (1 - q) * black(high, k, t, sigma, kind)


def fit_mixture(opts: pd.DataFrame, fwd: float, t: float, low: float):
    """Least-squares fit of (q, sigma); errors scaled so cheap options count."""
    rows = list(opts[["strike", "type", "close"]].itertuples(index=False))

    def loss(x):
        q, sig = x
        err = 0.0
        for k, kind, px in rows:
            model = mixture_price(fwd, k, t, sig, q, low, kind)
            err += ((model - px) / (px + 0.25)) ** 2
        return err

    best = None
    for q0 in (0.02, 0.1, 0.3):
        for s0 in (0.4, 0.8):
            r = minimize(
                loss, [q0, s0], bounds=[(0.0, 0.9), (0.05, 3.0)], method="L-BFGS-B"
            )
            if best is None or r.fun < best.fun:
                best = r
    return best.x[0], best.x[1], best.fun / len(rows)


def fit_fixed(opts: pd.DataFrame, fwd: float, t: float, low: float, sigma: float):
    """Same two-outcome model, but ordinary noise is held at the stock's own
    recent realised volatility, so any extra option value goes to the jump."""
    rows = list(opts[["strike", "type", "close"]].itertuples(index=False))

    def loss(q):
        return sum(
            ((mixture_price(fwd, k, t, sigma, q, low, kind) - px) / (px + 0.25)) ** 2
            for k, kind, px in rows
        )

    r = minimize_scalar(loss, bounds=(0.0, 0.9), method="bounded")
    return r.x, r.fun / len(rows)


def analyse(ticker: str, stock: pd.DataFrame, opts: pd.DataFrame) -> list[dict]:
    spot = stock[stock.ticker == ticker].set_index("date").close
    # normal swing size known on each day: Jul 1 up to that day, nothing later
    trailing = np.log(spot).diff().expanding(min_periods=20).std() * math.sqrt(252)
    out = []
    for (day, exp), g in opts[opts.ticker == ticker].groupby(["date", "expiry"]):
        if day not in spot.index:
            continue
        s = float(spot[day])
        d0, d1 = date.fromisoformat(day), pd.Timestamp(str(exp)).date()
        t = (d1 - d0).days / 365.0
        if t <= 0:
            continue
        fwd = s * math.exp(RATE * t)
        base_vol = float(trailing[day])
        g = g[g.volume > 0].copy()
        otm = g[
            ((g.type == "C") & (g.strike >= s)) | ((g.type == "P") & (g.strike <= s))
        ].copy()
        otm["iv"] = [
            implied_vol(p, fwd, k, t, c)
            for p, k, c in zip(otm.close, otm.strike, otm.type)
        ]
        otm["dist"] = np.abs(np.log(otm.strike / s))
        near = otm[(otm.dist < 0.10) & otm.iv.notna()]
        if near.empty:
            near = otm[(otm.dist < 0.15) & otm.iv.notna()]
        atm_iv = (
            float(np.average(near.iv, weights=1 / (near.dist + 0.02)))
            if len(near)
            else np.nan
        )
        straddle = (
            black(fwd, fwd, t, atm_iv, "C") + black(fwd, fwd, t, atm_iv, "P")
            if not np.isnan(atm_iv)
            else np.nan
        )
        # real straddle: call and put at the same strike, both traded, strike within 5%
        both = g.pivot_table(index="strike", columns="type", values="close")
        traded = np.nan
        if {"C", "P"} <= set(both.columns):
            both = both.dropna()
            both = both[np.abs(np.log(both.index / s)) < 0.05]
            if len(both):
                k = min(both.index, key=lambda x: abs(x - s))
                traded = (both.loc[k, "C"] + both.loc[k, "P"]) / s
        row = {
            "ticker": ticker,
            "date": day,
            "expiry": d1.isoformat(),
            "days_to_expiry": (d1 - d0).days,
            "spot": round(s, 2),
            "atm_iv": round(atm_iv, 3) if not np.isnan(atm_iv) else np.nan,
            "implied_move_pct": round(100 * straddle / s, 1)
            if not np.isnan(straddle)
            else np.nan,
            "straddle_traded_pct": round(100 * traded, 1)
            if not np.isnan(traded)
            else np.nan,
            "n_options": len(otm),
        }
        if not np.isnan(base_vol):
            base = black(fwd, fwd, t, base_vol, "C") + black(fwd, fwd, t, base_vol, "P")
            row["base_move_pct"] = round(100 * base / s, 1)
        if d0 >= RULING:
            out.append(row)  # the ruling is out; there is no pending crash to price
            continue
        low = LOSS.get(ticker, s * (1 + UTHR_JUMP))
        if ticker == "LQDA":
            puts = otm[
                (otm.type == "P") & (otm.strike > low + 10) & (otm.strike <= min(s, 60))
            ]
            if len(puts):
                p = puts.sort_values("volume").iloc[-1]
                row["q_put"] = round(p.close / (p.strike - low), 3)
                row["q_put_strike"] = p.strike
        else:
            calls = otm[(otm.type == "C") & (otm.strike < low - 5) & (otm.strike >= s)]
            if len(calls):
                c = calls.sort_values("volume").iloc[-1]
                row["q_put"] = round(
                    c.close / (low - c.strike), 3
                )  # call version for UTHR
                row["q_put_strike"] = c.strike
        if len(otm) >= 3 and not np.isnan(base_vol):
            q, err = fit_fixed(otm, fwd, t, low, base_vol)
            row.update(q_fixed=round(q, 3), fixed_err=round(err, 4))
            row["q_fixed_per_30d"] = round(
                1 - (1 - q) ** (30 / row["days_to_expiry"]), 3
            )
        if len(otm) >= 4:
            q, sig, err = fit_mixture(otm, fwd, t, low)
            row.update(
                q_mix=round(q, 3), sigma_mix=round(sig, 3), fit_err=round(err, 4)
            )
        out.append(row)
    return out


def realised_vol(stock: pd.DataFrame, ticker: str, start: str, end: str) -> float:
    c = stock[
        (stock.ticker == ticker) & (stock.date >= start) & (stock.date <= end)
    ].close
    r = np.log(c).diff().dropna()
    return float(r.std() * math.sqrt(252))


def charts(df: pd.DataFrame) -> None:
    pre = df[
        (df.ticker == "LQDA")
        & (df.date < RULING.isoformat())
        & (df.date >= "2026-08-01")
    ]
    oct16 = pre[pre.expiry == "2026-10-16"].sort_values("date")
    jan15 = (
        pre[pre.expiry == "2027-01-15"]
        .sort_values("date")
        .dropna(subset=["implied_move_pct"])
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        pd.to_datetime(oct16.date),
        oct16.implied_move_pct,
        color=GREEN,
        lw=2,
        label="Options expiring Oct 16",
    )
    ax.plot(
        pd.to_datetime(oct16.date),
        oct16.base_move_pct,
        color=GREEN,
        lw=1,
        ls=":",
        label="Oct 16, if priced at LQDA's normal swings",
    )
    ax.plot(
        pd.to_datetime(jan15.date),
        jan15.implied_move_pct,
        color="#5b6f8f",
        lw=2,
        label="Options expiring Jan 15, 2027",
    )
    ax.axhline(57.2, color=RED, ls="--", lw=1.5)
    ax.text(pd.Timestamp("2026-08-03"), 58.5, "Actual drop on Sept 30: 57%", color=RED)
    ax.set_ylim(0, 65)
    ax.set_ylabel("Price of a straddle, as % of the stock price")
    ax.set_title(
        "On Sept 29, LQDA options priced a 17% move by Oct 16; the stock fell 57%"
    )
    ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1, 0.86))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "Straddle = one call plus one put at the stock price. Source: Yahoo Finance daily "
        "option closes.\nNormal swings = LQDA realised volatility from Jul 1 to each day "
        "(61% on Sept 29).",
        fontsize=8,
        color="#555",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(HERE / "lqda_implied_move.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    jan15 = pre[pre.expiry == "2027-01-15"].sort_values("date")
    for g, color, label in [
        (oct16, GREEN, "Before Oct 16"),
        (jan15, "#5b6f8f", "Before Jan 15, 2027"),
    ]:
        g = g.dropna(subset=["q_fixed", "q_mix"])
        x = pd.to_datetime(g.date)
        ax.fill_between(
            x,
            100 * g[["q_fixed", "q_mix"]].min(axis=1),
            100 * g[["q_fixed", "q_mix"]].max(axis=1),
            color=color,
            alpha=0.25,
            lw=0,
        )
        ax.plot(
            x,
            100 * g[["q_fixed", "q_mix"]].mean(axis=1),
            color=color,
            lw=2,
            label=label,
        )
    ax.scatter([pd.Timestamp("2026-09-30")], [100], color=RED, zorder=5)
    ax.text(
        pd.Timestamp("2026-09-27"),
        95,
        "What happened: Liquidia\nlost on Sept 30",
        color=RED,
        ha="right",
    )
    ax.set_ylim(0, 105)
    ax.set_ylabel("Priced chance LQDA falls to about $30 (%)")
    ax.set_title("Options priced about a 1-in-5 chance of the crash before mid-January")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 0.75))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "Band = range of the two fitting methods in the report; line = their average. "
        "Odds read from option prices (risk-neutral), not a forecast.",
        fontsize=8,
        color="#555",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(HERE / "lqda_loss_odds.png", dpi=150)
    plt.close(fig)


def sensitivity(
    stock: pd.DataFrame, opts: pd.DataFrame, base_vol: float
) -> pd.DataFrame:
    """Sept 29 LQDA odds under different guesses of where a loss sends the stock."""
    day = "2026-09-29"
    s = float(stock[(stock.ticker == "LQDA") & (stock.date == day)].close.iloc[0])
    rows = []
    for exp in ("2026-10-09", "2026-10-16", "2026-11-20", "2027-01-15"):
        g = opts[
            (opts.ticker == "LQDA")
            & (opts.date == day)
            & (opts.volume > 0)
            & (opts.expiry == int(exp.replace("-", "")))
        ]
        g = g[((g.type == "C") & (g.strike >= s)) | ((g.type == "P") & (g.strike <= s))]
        t = (date.fromisoformat(exp) - date.fromisoformat(day)).days / 365.0
        fwd = s * math.exp(RATE * t)
        for low in (25.0, 30.26, 35.0, 40.0):
            qf, _ = fit_fixed(g, fwd, t, low, base_vol)
            qm, sig, _ = fit_mixture(g, fwd, t, low)
            rows.append(
                {
                    "expiry": exp,
                    "loss_price": low,
                    "q_fixed": round(qf, 3),
                    "q_mix": round(qm, 3),
                    "sigma_mix": round(sig, 3),
                    "win_price_fixed": round((fwd - qf * low) / (1 - qf), 2),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    stock = pd.read_csv(HERE / "stock_daily.csv")
    opts = pd.read_csv(HERE / "option_daily.csv")
    opts = opts[opts.date <= "2026-10-09"]
    vols = {
        t: realised_vol(stock, t, "2026-07-01", "2026-09-29") for t in ("LQDA", "UTHR")
    }
    print("realised vol Jul 1-Sep 29:", {k: round(v, 3) for k, v in vols.items()})
    rows = analyse("LQDA", stock, opts) + analyse("UTHR", stock, opts)
    df = pd.DataFrame(rows).sort_values(["ticker", "date", "expiry"])
    df.to_csv(HERE / "implied_by_day.csv", index=False)
    sensitivity(stock, opts, vols["LQDA"]).to_csv(
        HERE / "loss_price_sensitivity.csv", index=False
    )
    charts(df)


if __name__ == "__main__":
    main()
