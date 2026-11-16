# Lawsuit-driven stock moves

Research only. Nothing here is investment advice.

**Executive summary**
- **What this is:** a database of US court rulings that moved a public company's stock. For each one it records the minute the ruling appeared on the court's public docket (the court's list of every filing in a case) and how the stock moved afterwards.
- **Why it matters:** court rulings go onto the public docket before any press release or SEC filing. If a stock still has most of its move ahead of it a minute after the filing, a fast, legal watcher of public court records has a trading edge.
- **Where we looked:** 40 candidate rulings from 2023 to 2026: drug patents, antitrust and merger cases, and jury verdicts. Filing times come from the free RECAP court archive at https://www.courtlistener.com/. Daily prices come from Yahoo, and one-minute prices from Polygon.io.
- **What we found:**
  - 18 of the 40 candidates matched the real ruling on the docket, after checking each by hand.
  - 9 of those 18 have an exact filing time and fall inside Polygon's free 2-year window, covering 13 stocks.
  - In 6 of the 7 stocks that moved more than 3%, at least 66% of the move was still there one minute after the filing. The exception was CPRI, at 18%. One of the 6, ACI, moved late only because the opinion was sealed.
- **Still open:**
  - The sample is small.
  - After-hours trading is thin, so a real order could move the price itself.
  - We haven't measured how fast the courts' public feeds show a new filing.
  - Whether rulings bunch up before the March 31 and September 30 reporting cutoffs is untested. RECAP's search allows 50 requests an hour without an account, and the test needs about 240 (`scripts/cjra_clustering.py`).

## Full case lists (2021 to now)
- Combined results across all seven case types, including the Liquidia-style count per year: `docs/combined_universe.md`.
- Trading rulings from the minute they were posted (backtest): `docs/intraday_backtest.md`.
- Plan for a live ruling monitor, with measured court RSS delays: `docs/live_monitor_plan.md`.
- One write-up per case type in `docs/universe_*.md`, and prior research in `docs/prior_research.md`.

## Terms
- **Docket entry:** one line on a court case's public list of filings, with a time stamp.
- **Filing time:** the minute the court entered the ruling on the docket. RECAP shows it on each document's page as "Date Filed".
- **Move left after 1 minute:** the share of the move, from the last trade before the filing to the close, that still lay ahead one minute after the filing. 100% means the price hadn't moved yet; 0% means it was already at the close.
- **After hours:** trading after the 16:00 ET close (and before the 9:30 open). Fewer shares change hands.

## First-minute results
Each row shows the last trade before the filing, the price 1 and 5 minutes after, and the close of the first full session after the ruling. All times are ET.

- **Google search remedies, 2 Sept 2025, 16:05 (after the close)**
  - **GOOGL:** $211.35 before, $211.04 at +1 minute, $218.00 at +5, $230.63 at the next close (+9.1%). The move left after 1 minute was 102%: the price hadn't moved yet.
  - **AAPL:** $229.30 before, $229.36 at +1 minute, $238.49 at the close (+4.0%). 99% left.
- **Liquidia (LQDA) patent opinion, 30 Sept 2026, 11:21**
  - **LQDA:** $62.17 before, $55.33 at +1 minute, $30.17 at the close (−51.5% from the minute before). 79% left. An earlier order at 11:15 had already started the fall from about $71.60.
  - **UTHR:** $503.01 before, $515.80 at +1 minute, $541.68 at the close (+7.7%). 67% left.
- **Tapestry–Capri merger blocked, 24 Oct 2024, 16:03 (after the close)**
  - **CPRI:** $35.00 before, $23.75 at +1 minute, $21.26 at the next close (−39.3%). Only 18% left: after-hours sellers reacted inside the minute.
  - **TPR:** $44.92 before, $46.81 at +1 minute, $50.25 at +5, $50.50 at the close (+12.4%). 66% left after 1 minute, about 5% after 5.
- **Kroger–Albertsons blocked, 10 Dec 2024, 13:45**
  - **KR:** +2.4% to the close, and almost nothing in the first hour.
  - **ACI:** −3.7% to the close, the same pattern.
  - The opinion was filed under seal, so the docket entry didn't show who won.
- **Rulings that didn't move the stock (under 2%):** Meta (FTC monopoly case), Exelixis, Novartis (Entresto), AstraZeneca (Calquence), Pfizer.

## Could the ruling date have been guessed?
`scripts/ruling_timing.py` looks on each ruling's docket for the last post-trial step: a post-trial brief, proposed findings, a closing argument or the last day of trial. It found one for only 5 of the 19 usable rulings; the rest have no public docket text with those words. Of the 5, two make sense:
- **Liquidia:** the last post-trial filing was 6 Aug 2025 (D.I. 441, about the reply post-trial brief). The ruling came 420 days later, on 30 Sept 2026, the day of a six-month-list cutoff.
- **Google ad tech:** the bench trial ended 25 Nov 2024. The ruling came 143 days later.
- **Exelixis:** post-trial documents were filed 27 Feb 2024. The ruling came 239 days later.
- **Not usable:** the Kroger and 2024 Google rows matched sealing motions, not post-trial steps.

So, from what we have: the waits ranged from about 5 months to 14 months, and 1 of 19 rulings fell in the two weeks before a cutoff. That says nothing yet about clustering.

## Files
- `scripts/lawsuit_moves.py`: searches RECAP around each candidate's date for an opinion, order, verdict or judgment. It reads the exact filing time from the document's public page and adds the one-day move from Yahoo daily prices. Output: `data/lawsuit_moves.csv`. It takes about 2 hours, because RECAP allows about one request every 6 seconds without an account.
- `scripts/review.py`: the hand check of every automatic match: ok, needs_check, wrong_document or no_match, with a note. Output: `data/lawsuit_moves_reviewed.csv`. The automatic pick sometimes lands on a motion or a stipulation, so use the reviewed file.
- `scripts/minute_backtest.py`: pulls one-minute prices from Polygon.io (needs `POLYGON_API_KEY`; the free plan goes back about 2 years at 5 requests a minute). Output: `data/minute_backtest.csv`.
- `scripts/ruling_timing.py`: for each ruling, finds the last post-trial filing or hearing on the same docket, the days from it to the ruling, and whether the ruling fell in the 14 days before a March 31 or September 30 cutoff. Output: `data/ruling_timing.csv`.
- `scripts/cjra_clustering.py`: counts post-trial opinions in every half-month from 2016 to 2025, to test whether judges rush rulings out before the March 31 and September 30 cutoffs. The cutoffs come from the Civil Justice Reform Act, a law that makes courts publicly list every motion and bench trial a judge has held for more than 6 months. Output: `data/cjra_halfmonth_counts.csv`.
- `options/`: what LQDA and UTHR option prices implied about the Liquidia ruling.

## Limits
- Raw prices are not in the repo, because Polygon and Yahoo do not allow republishing them. The fetch scripts download them again: `scripts/minute_backtest.py` and `scripts/intraday_backtest.py` need `POLYGON_API_KEY`. `options/fetch_options.py` refetches the stock prices, but Yahoo no longer serves option contracts that have expired, so the option analysis can't be rerun in full; its results are in `options/implied_by_day.csv`. Set `CONTACT_EMAIL` so SEC EDGAR gets a contact address.
- **Only public records:** no PACER logins, paywalls or unpublished documents.
- **Filing times are to the minute,** not the second.
- **Prices:** the "+1 minute" price is the close of the bar that started one minute after the filing minute.
- **After-hours bars are sparse,** and a minute with no trades carries the last price forward.
- **Rulings before about Oct 2024** have daily moves only. This includes Pacira (−47.7%), Corcept, Natera v NeoGenomics (NEO −18.1%) and the 2024 Google liability ruling, which landed on a market-wide sell-off day.
- **Exact times are missing for some rulings:** where RECAP's page shows only a date, the row has `clock_time_known=False` and is left out of the minute test. These include Acadia's Nuplazid ruling (+26.5% on the day), Lantheus, Vertex and Novo.
- **No intraday option prices:** no free source exists.
