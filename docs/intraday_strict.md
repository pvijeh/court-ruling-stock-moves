# Stricter rerun of the intraday backtest

Script: `scripts/intraday_strict.py`. Output: `data/universe/combined/intraday_strict.csv`.
Same trade as `docs/intraday_backtest.md`: enter after the posting time, exit at the close, minus SPY/XBI over the same window, direction from who won.

## Why rerun

An audit of the first backtest found the sample was mostly noise:
- 247 of 558 trades were PTAB institution denials, not decisions on the merits.
- 443 were on the challenger side, mostly mega caps (Alphabet, Apple, Microsoft).
- 111 rulings were traded on both sides.
- Market cap was blank for 411 trades.
- In the 36 stock-days that moved more than 5%, the biggest 5-minute move came a median 133 minutes before the posting time, and about 72% of the day's move came before posting.

## Filters

- PTAB: final written decisions only. Other case types kept as they were.
- Company worth under $5B on the ruling day: Polygon shares outstanding (`/v3/reference/tickers/<T>?date=`) times the last price before posting.
- One side per ruling: the smallest listed company.
- Entry clock: the earliest posting time among the rulings that passed these filters. A dropped ruling earlier the same day doesn't start the trade.
- Drop stock-days that already moved 3% or more against the benchmark between the 9:30 open and the posting time. That move is visible before entry, so this filter uses no hindsight.

## Labels fixed first

`scripts/ptab_label_audit.py` reads each PTAB final decision's caption ("Determining All / No / Some Challenged Claims Unpatentable") and compares it with our win/loss label. The ORDER paragraph is a second reading. Output: `data/universe/ptab/label_audit.csv`.
- 541 rows checked: 448 agreed and 38 rows (27 cases) were relabelled. 49 had no decision document in P-TACTS, 9 couldn't be read, and 2 are left for a hand check (MDT IPR2022-00431, SATS IPR2024-00373).
- Most of the errors were remands. The Board issued a new final decision after a Federal Circuit remand, and our data still carried the original one. Example: Universal Electronics on 2025-03-10 (IPR2021-00455) was a loss on remand ("All Challenged Claims Unpatentable") but was labelled a win.
- `scripts/universe_ptab.py` now picks the final decision posted nearest the case's end date, including remand decisions.
- 9 relabels were checked by hand against the PDF, 5 of them picked at random. All 9 were right.

## Result

After the label fixes:
- 36 stock-days passed the type, size and one-side filters. 27 were left after the pre-move filter, and 26 had a trade.
- **All 26 are PTAB.** Every non-PTAB event in the window (Kroger/Albertsons, Novartis, Google, Meta, Oracle, Tesla and others) is above $5B.

| Entry delay | Trades | Mean | Median | Hit rate | t-stat | Mean after 5 bp each way |
|---|---|---|---|---|---|---|
| +0 min | 26 | +0.39% | +0.28% | 62% | 0.74 | +0.29% |
| +1 min | 26 | +0.45% | +0.30% | 62% | 1.05 | +0.35% |
| +2 min | 26 | +0.38% | +0.27% | 62% | 0.92 | +0.28% |
| +5 min | 26 | +0.34% | +0.15% | 54% | 0.84 | +0.24% |
| +15 min | 22 | +0.45% | +0.43% | 73% | 0.93 | +0.35% |

## Second pass: earnings, prior close, liquidity

Script: `scripts/intraday_strict2.py`. Output: `data/universe/combined/intraday_strict2.csv`. +1 minute entry. It adds:
- Earnings: drop the stock-day if the company released results between the prior close and the event day's close (SEC 8-K item 2.02 acceptance time; for foreign filers, a 6-K that Nasdaq's earnings calendar also lists). This dropped 2: Genius Sports on 2026-03-04 and Immersion on 2025-07-31.
- Already moved: stock minus benchmark from the prior session's close to the minute before posting, so overnight gaps count. Dropped if 3% or more either way. This dropped 10.
- Liquidity: 20-session average dollar volume before the event day.
- Costs: each stock-day's spread estimated from its own minute bars (Abdi and Ranaldo 2017), with a median of 0.07%.

| Min. daily $ volume | Trades | Stocks | Mean | Median | Hit rate | t-stat | Mean after spread | t-stat after spread | t-stat, each stock once |
|---|---|---|---|---|---|---|---|---|---|
| none | 23 | 15 | +0.78% | +0.63% | 70% | 1.91 | +0.67% | 1.57 | 1.24 |
| $1M | 19 | 12 | +0.90% | +0.63% | 68% | 1.89 | +0.84% | 1.74 | 1.32 |
| $5M | 14 | 9 | +1.30% | +0.76% | 79% | 2.12 | +1.23% | 1.99 | 1.66 |
| $10M | 10 | 7 | +1.63% | +0.90% | 90% | 1.98 | +1.57% | 1.89 | 1.35 |

## Reading

Close to the usual t-stat of 2, but not evidence of an edge:
- 14 to 23 trades in 7 to 15 stocks. Counted one per stock, no row clears 1.7.
- The earnings filter was added after looking at the losing trades in the first run, which biases the result upward.
- `scripts/posting_time_check.py` found that PTAB postings rarely move volume. Only about 1 in 30 stock-days had a minute at 10 times normal volume within 2 minutes of posting, roughly what chance gives. So the small positive mean may not come from the ruling at all.

This still says nothing about drug-patent or merger rulings. None of them in the free two-year minute window are under $5B, and most only had a date, not a minute. See `docs/timing_check.md`.

## Caveats

- Share counts come from Polygon's reference endpoint for one date per ticker (the ticker's first ruling in the sample). They are approximate for multi-class issuers.
- The 3% pre-move cutoff and $5B cap were chosen before the first run, not tuned. The volume cutoffs are all shown because none was fixed in advance.
