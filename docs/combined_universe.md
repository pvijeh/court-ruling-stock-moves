# All seven case types combined: how many Liquidia-style rulings happen a year

**Executive summary**
- **What this is:** one table that joins the seven case lists in `data/universe/` (drug-patent trials, government merger challenges, Delaware and deal suits, business-practice antitrust, jury verdicts, ITC import-ban cases and patent-office PTAB trials). It counts how often a ruling moves a listed company's stock, and how often that ruling comes out while the market is open on a day nobody knew in advance.
- **Why it matters:** a "Liquidia-style" ruling is the trade this project is looking for. A judge or board posts a decision mid-session with no warning, the stock moves more than 10%, and the company's own release comes hours later. Knowing how many happen a year sets the ceiling on what a fast alert could earn.
- **Where we looked:** 7,444 company rows from 2021 to October 2026. After merging rows that are the same stock on the same day, 1,624 decided events have a decision-day price.
- **What we found:**
  - About 4 Liquidia-style rulings a year across all seven types (estimate). Drug patents give about 1.4 a year and PTAB about 2.2. The rest give about 0.5 between them.
  - Company size is the strongest sign of a big move. Under $1B market cap, 17% of rulings moved the stock more than 10%; over $10B, 2% did.
  - Facts known when a case is filed don't predict the size of the move much better than guessing the typical move. They do help rank cases: the top 10% by model score hold about 3 to 4 times the base rate of big moves.
- **Still open:** posting times exist mainly for PTAB and for drug patents from 2023 on. ITC and jury-verdict rows have none. PTAB prices only cover about two years, and some big PTAB moves at large companies are probably other news.

**Terms**
- *Abnormal move*: the stock's decision-day return minus the benchmark's (XBI for drug companies, SPY for the rest), as recorded by each case list.
- *Event*: one stock on one decision day. Several PTAB trials decided the same day for the same company share one price move, so they count once.
- *Unscheduled*: nobody knew the date in advance (`decision_known_in_advance = no`).
- *Timed*: the row has a posting minute or hour, or a time inferred from the first price jump.
- *Fast-alert event*: an unscheduled, timed decision that came out between 9:30 and 16:00 ET. Settlements and withdrawals are left out, because the parties know first.

## How many Liquidia-style rulings a year

**Method**
- For each case type, count the unscheduled decided events that moved the stock more than 10% (not settlements), per year of price coverage.
- Multiply by the share of timed, unscheduled decisions in that type that came out during market hours. Settlements and withdrawals are left out of this share too.
- This assumes the untimed rulings come out during market hours as often as the timed ones. That is a guess, and the timed samples are small outside PTAB.

**Estimate by case type**
- **Drug patents:** 2.0 unscheduled 10%+ moves a year × 71% in market hours (14 timed rows) ≈ **1.4 a year**.
- **PTAB:** 8.5 a year × 26% in market hours (3,887 timed rows) ≈ **2.2 a year**. Counted directly, 8 fast-alert events moved more than 10% in about two years of prices, which is 4 a year. Ford, Micron, Ericsson and Roku are among them, and large-company moves that size are more likely other news.
- **Merger challenges:** 0.8 a year × 25% (8 timed rows) ≈ 0.2 a year.
- **Delaware and deal suits:** 0.4 a year × 60% (35 timed rows) ≈ 0.2 a year.
- **Business-practice antitrust:** 0.2 a year × 75% (4 timed rows) ≈ 0.1 a year.
- **Jury verdicts:** none. Every verdict date was known from the trial schedule.
- **ITC import bans:** unknown. 0.35 unscheduled 10%+ moves a year, but the ITC only shows posting times after a login, so no row is timed.

**Observed, not estimated:** 9 fast-alert events moved more than 10%: Pacira −48% (drug patent, 2024-08-09, sealed opinion at 15:17) and 8 PTAB rows. The largest PTAB ones were Biofrontera +18%, Ericsson −14%, Ford +13%, CommScope +12% and Hesai +12%. The full list, sorted by move, is `data/universe/combined/fast_alert_events.csv`.

## Size of moves by case type

All counts are decided events from 2021 on with a price. When several rows share a stock and day, one is kept: a decided, priced row from the more specific case type. A pending row doesn't hide a decided one on the same day.

- **Drug patents:** 93 events over 5.5 years. Median move 2.2%. 25 over 5%, 11 over 10%, 5 over 25%.
- **Merger challenges:** 38 events over 5.2 years. Median 3.7%. 14 over 5%, 6 over 10%, 2 over 25%.
- **Delaware and deal suits:** 57 events over 5.5 years. Median 1.3%. 7 over 5%, 3 over 10%, 1 over 25%.
- **Business-practice antitrust:** 60 events over 5.6 years. Median 1.6%. 5 over 5%, 2 over 10%, none over 25%.
- **Jury verdicts:** 104 events over 5.6 years. Median 1.4%. 13 over 5%, 6 over 10%, 2 over 25%.
- **ITC import bans:** 283 events over 5.7 years. Median 1.7%. 40 over 5%, 10 over 10%, 1 over 25%.
- **PTAB:** 989 events over 2.0 years. Median 1.2%. 79 over 5%, 19 over 10%, 1 over 25%.

## Company size

Small companies move the most, which matches the Liquidia, Pacira and Heron cases. Market cap is the value each case list recorded at filing.

- **Under $1B:** 72 events, median move 3.0%, 16.7% moved more than 10%.
- **$1B to $10B:** 140 events, median 2.2%, 7.1% over 10%.
- **Over $10B:** 568 events, median 1.4%, 1.8% over 10%.
- **Unknown:** 844 events (mostly PTAB), median 1.2%, 3.0% over 10%.

## Head start and price speed

The numbers here are thin. Only 7 fast-alert events have a company release time to compare against, and most minute-level speeds come from PTAB.

- **Lead over the company's own release:** drug patents median 281 minutes (Exelixis 315, Pacira 246). Business-practice antitrust: Alphabet's search ruling came 326 minutes ahead. The merger and deal-suit medians of 1,594 and 2,416 minutes mean the company waited until the next day or later.
- **Minutes to half the day's move:** PTAB median 46 minutes (269 events). Merger challenges about 1 minute (2 events, Kroger and Albertsons). Deal suits 38 minutes (6 events). The drug-patent session reported that Exelixis moved within its first minute, but that figure isn't in the `minutes_to_half_move` column.

## Can the move be predicted when the case is filed?

**Test**
- The target is the size of the abnormal move on decision day, ignoring direction. Direction depends on who wins, which isn't known at filing.
- Walk-forward: for each test year from 2023 to 2026, train only on earlier decision years, then predict that year. 1,380 test events, or 391 without PTAB.
- Features known at filing: case type and company role, market cap, share of revenue at stake (filled for drug patents, merger challenges and jury verdicts only) and whether the date is scheduled. A second version adds 20-day dollar trading volume before the decision. That is known before the ruling but not at filing.
- Models: the training-years median for each case type, a ridge regression (a linear fit that keeps the weights small) and boosted trees (many small decision trees added together).

**Result**
- None of the models gets closer to the actual move than guessing the median move of the earlier training years. On all events that guess misses by 1.8 points on average; the best model also misses by 1.8.
- Ranking works better than size. 3.3% of test events moved more than 10%. Among the 10% of events the models ranked highest, 9–14% did, depending on the model. Those top-ranked events hold 29–42% of all the big moves. The top tenth is exactly 10% of events; tied scores are broken at random with a fixed seed.
- Without PTAB, 6.6% of test events moved more than 10%, against 13–18% in the top-ranked tenth.
- Results by model are in `data/universe/combined/prediction_walkforward.csv`.

**What this means:** these filing-day facts can pick which pending cases to watch, mostly through company size and case type. They can't say how far the stock will move. A better forecast needs facts these lists don't have yet: revenue at stake for every case, option prices before the ruling and who is expected to win.

## Files

- `scripts/combine_universe.py` rebuilds everything from the seven `cases.csv` files. Run `python3 scripts/combine_universe.py`.
- `data/universe/combined/cases.csv`: every row, with `category`, `event_key` (ticker and decision date) and `dup_of_category` for rows that repeat another type's event.
- `summary_by_category.csv`, `moves_by_company_size.csv`, `fast_alert_events.csv` and `prediction_walkforward.csv` hold the numbers above.

## Gaps

- **Posting times:** only 16% of drug-patent rows are timed, all from 2023 on. Merger challenges are at 17%, antitrust at 11%, and ITC and jury verdicts have none. The yearly estimate leans on those small timed samples.
- **Prices:** PTAB prices start around October 2024 because Yahoo blocked requests and Polygon's free data covers about two years. Delisted and over-the-counter stocks have no price in any list.
- **Other news:** no list removes days with earnings or other company news, apart from rows flagged by hand in the notes. Large-company PTAB moves are the most exposed.
- **Legislation:** not included. It will be a separate dataset.
