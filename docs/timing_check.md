# Was the posting minute the first public moment?

The Liquidia ruling on 2026-09-30 is the model. D.I. 474 hit the Delaware docket at 11:15 ET. Liquidia traded 318,713 shares in that minute, about 230 times its normal minute volume, and fell sharply. The company's press release came about two hours later. A posting time that really is the first public moment should look like that: the volume spike in the posting minute, not before it.

## PTAB postings (`scripts/posting_time_check.py`)

For each of the 671 stock-days in `intraday_backtest.csv`, using the cached minute bars:
- volume in the posting minute and the 2 after it, over the median minute volume in the quiet minutes before posting (9:40 to 15:50 only, to leave out the open and close)
- the first minute at 10 times that median, relative to posting
- the share of the open-to-close abnormal move that came before posting

Output: `data/universe/combined/posting_time_check.csv`.

- 637 stock-days had minute bars. 21 had a 10x minute within 2 minutes of posting. Chance alone gives about 19, from how often each stock has a 10x minute on a normal stretch of the day.
- 625 of the 637 are PTAB: 19 had a 10x minute at posting, against about 18.5 expected by chance.
- Of the 31 stock-days that moved 5% or more, 3 reacted at posting: Kroger on the Albertsons merger ruling (2024-12-10, 71x), Network-1 (NTIP, PTAB, 2026-05-06, 38x, +6%) and Genius Sports (PTAB, 2026-03-04, 18x, an earnings day). On the rest, a median 64% of the day's move came before posting.
- The PTAB timestamps themselves look right. P-TACTS stamps each upload to the second. The market mostly just doesn't trade on them.

## Court rulings that only had a date (`scripts/court_minute_times.py`)

For each non-PTAB ruling in the minute-price window (138 rows), the script looks up the case on CourtListener and takes the earliest docket entry on the decision day that reads like the ruling, with CM/ECF's filing time converted from the court's local time to ET. Entries filed under seal are skipped, because the outcome wasn't public at that minute. Rows with a minute during market hours get the same volume check and the same trade as above. Output: `data/universe/combined/court_minute_times.csv`.

Our CourtListener token allows 50 calls an hour and 125 a day, so the run took two days. It checks the biggest moves first and saves after every ruling; a rerun picks up from the cache.

| What the docket showed | All 138 | Moved 5%+ |
|---|---|---|
| Timed to the minute | 18 | 4 |
| ITC (its document site blocks this machine) | 35 | 5 |
| No docket number in our data | 23 | 4 |
| State court | 18 | 3 |
| Delaware Chancery or Supreme Court | 15 | 2 |
| No ruling entry on the decision day | 12 | 1 |
| Federal Circuit (opinions have no posting time) | 11 | 4 |
| Ruling entry has no filing time | 4 | 0 |
| Ruling filed under seal, made public later | 2 | 1 |

Party filings that only mention a ruling (proposed verdict forms, stipulations, motions) are not counted as the ruling. That is why Regeneron and Amgen (2025-05-14) aren't timed: the only same-day entry was Regeneron's proposed verdict form.

The 18 timed rulings:
- Kroger and Albertsons, 2024-12-10: the Oregon opinion blocking the merger was filed at 15:21 ET (12:21 Pacific). Kroger traded 71x normal volume in that minute and Albertsons 225x. This is the one Liquidia-type reaction in the window.
- Teva, J&J and Viatris, 2024-12-17: the public version of a sealed patent opinion was posted at 15:28, with no spike (1.4x to 4.9x). Teva's +33% that day came from its own drug-trial data released that morning, not the ruling.
- Apple (2025-06-30), State Street and BlackRock (2025-08-01), Novartis (2025-07-11, 10:01) and Meta (2025-11-18, 12:39) were filed during market hours with no spike (1.3x to 3.8x).
- Live Nation, 2026-02-18: a summary-judgment order at 15:57 shows 222x, but that is the closing rush (the baseline leaves out 15:50 to 16:00) and the price drifted rather than jumped. There's no time left for a 1-minute trade before the close.
- Alphabet (2025-09-02, 16:05), Intuitive Surgical (2025-01-27, 17:06), Deere (2025-06-09, 17:04), Apple v. Epic (2025-04-30, 18:06), Live Nation's verdict (2026-04-15, 18:37), and Nexstar and Tegna (2026-04-17, 20:41) were docketed outside market hours, so there's no first-minute trade. For jury verdicts like Live Nation's, the verdict is read in court before the form reaches the docket, so the docket time is late.

The sealed rulings show why the docket isn't always the first public source. Heron (HRTX), 2024-12-03: the findings were filed under seal at 11:36 and unsealed on 12-16. Heron traded about 10x its usual daily volume on 12-03, starting at 09:54, while the price fell. It then opened 68% higher on 12-04 on 61M shares. The market heard the result from something other than the docket, most likely the company. We haven't found that source yet.

## What this means

- The PTAB backtest timestamps are right, but PTAB rulings rarely move stocks, so that backtest can't tell us much about the Liquidia idea.
- Of all 138 non-PTAB rulings in the two years of minute prices we have, only Kroger/Albertsons reacted Liquidia-style at the docket minute. One event can't be backtested.
- The cases that could test the idea are timed somewhere other than CourtListener: ITC notices (EDIS), Federal Circuit opinions, sealed district-court opinions where the company announces first, and Delaware Chancery. Each needs its own first-source check, as Liquidia did.
- Liquidia's own ruling (2026-09-30) isn't in the case lists. The drug-patent list stops on 2026-08-31.
