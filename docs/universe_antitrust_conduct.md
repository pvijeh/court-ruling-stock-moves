# Government antitrust conduct suits, 2021 to Oct 2026: how much the stock moved

**Reader:** someone deciding whether court outcomes in antitrust cases can be predicted or traded, who has not seen this project.

**Main finding:** among 89 company-event rows, the stock's move against the market on the day of the outcome was usually small. The median was 1.5%. Only 8 rows moved more than 5%, and 2 of those 8 were caused by earnings reports, not the case.

## Summary

- **What this is:** a list of antitrust suits about business conduct brought by the US Department of Justice (DOJ), the Federal Trade Commission (FTC) or state attorneys general (AGs) against US-listed companies, filed or decided from Jan 1 2021 to Oct 14 2026. It also covers 8 private suits against listed companies that reached a jury verdict or liability ruling. Each row is one event (complaint, ruling, verdict, settlement) for one listed company.
- **Why it matters:** to estimate at filing how much a stock will move when the case is decided, you need every case, including the ones where nothing happened. A list of dramatic cases overstates the typical move.
- **Where we looked:** the FTC competition case list, DOJ Antitrust Division case pages (through the Internet Archive), Google News searches for every two-month window, earlier hand-checked court documents from CourtListener, and SEC filings.
- **What we found:** 38 cases, 89 rows, 36 tickers. Median absolute move against the market on decision day 1.5%; none over 25%. Only 3 outcomes came out during market hours on a date nobody knew in advance, and only 1 of them has minute-by-minute price data.
- **Still open:** most rows have no clock time for the outcome, because the CourtListener quota ran out (details below). The list is probably missing some state AG suits and some private verdicts.

## Terms used

- **Antitrust conduct suit:** a suit saying a company broke competition law by how it does business. Examples: **monopolization** (using a dominant position to keep rivals out), **exclusive dealing** (contracts that stop customers buying from rivals), **price fixing** (competitors agreeing on prices) and worker no-poach or noncompete deals. Suits to block a merger are left out.
- **Settlement / consent order:** the company and the government agree to end the case, usually with promises and sometimes a payment. A consent order is a settlement the court or the FTC makes binding.
- **Motion to dismiss:** the company asks the judge to throw the case out before any evidence is heard. Losing it means the case goes on.
- **Summary judgment:** a ruling before trial on claims where the facts are not in dispute.
- **Return:** the percent change in the stock's closing price from one trading day to the next, written as a decimal (0.05 = 5%).
- **Abnormal return:** the stock's return minus the return of the market on the same days. The market is the SPY fund (the S&P 500), or the XBI biotech fund for drug companies. A -4% abnormal return means the stock did 4 points worse than the market.
- **Market hours:** 9:30 am to 4:00 pm Eastern time on a trading day.

## What was counted and how

- **Government cases:** 30. Sources were the FTC competition case list (saved from ftc.gov, every page 2021 to today), the DOJ Antitrust Division case slugs in the Internet Archive (justice.gov returns HTTP 401 to this machine), and news searches for "sues", "antitrust", "settles", "verdict" and "ruling" plus DOJ, FTC or attorney general, in two-month windows.
- **Private cases:** 8 that reached a jury verdict or liability ruling against a listed defendant, such as Epic v. Apple, Epic v. Google, Regeneron v. Amgen and the realtor-commission verdict against Berkshire Hathaway's HomeServices.
- **Left out:** merger challenges; cases where no party is US-listed (Agri Stats, RealPage itself, Syngenta, Publicis, Dentsu, Vanguard); criminal cases against individual employees only.
- **Rows:** one per event per listed company. A case against three listed landlords has three rows per event. Both sides get a row when both are listed (Regeneron and Amgen).
- **Dates:** each event date was checked against at least one dated source: the FTC case timeline, a court document from the earlier hand review, or news on the same day. 19 rows where no news item within a day was found, or where the date came from one secondary report, are marked low confidence.
- **Confidence:** 4 rows high (date and clock time checked against the court document itself), 66 medium (date checked against an agency page or same-day news), 19 low.
- **Prices:** Yahoo daily closes, split- and dividend-adjusted. If the outcome's clock time is unknown, the decision-day return covers two days (that day and the next), so a ruling issued after the close is still captured. Filing-day returns are also two-day. Every row says so in its notes.
- **Company size at filing:** shares outstanding from SEC XBRL filings times the price on the filing date, and revenue over the prior 12 months from the same filings. Missing for Alphabet (its shares are reported by class), Berkshire and WPP (share classes or foreign shares make the number wrong).
- **Revenue at stake:** not filled for any row. Segment revenue for the product at issue was not collected.
- **Other news:** the 12 biggest moves were checked against that day's headlines. Two are caused by earnings and are marked CONFOUNDED in the notes.

## How complete the list is

- **FTC:** close to complete for conduct cases against listed companies, because the FTC publishes a full case list.
- **DOJ:** likely complete for civil conduct cases against listed companies. Less sure for criminal price-fixing pleas, which DOJ files often and news covers lightly.
- **State AGs:** the weakest part. There is no national list. Suits found by news search are included (D.C. and California v. Amazon, Texas v. BlackRock, the states' Google Play and Facebook cases). Smaller single-state suits are likely missing.
- **Private cases:** only those with a verdict or liability ruling found by news search. This is not a full list.
- **Events within a case:** complaints, settlements and major rulings are covered. Smaller motion rulings may be missing, mostly for state cases.
- **Quota limit:** the shared CourtListener account hit its 125-requests-a-day limit during this work (HTTP 429). That is why only 3 rows have a minute-level clock time from the court docket. 2 more rows take the minute from a company 8-K, 5 use same-day news (time is an upper bound) and 79 have the date alone.

## Counts

- **Cases by filing year:** 2011: 1, 2019: 2, 2020: 7, 2021: 7, 2022: 4, 2023: 4, 2024: 5, 2025: 4, 2026: 4. Cases filed before 2021 are included because they had events after Jan 1 2021.
- **Events by year:** 2021: 10, 2022: 7, 2023: 14, 2024: 11, 2025: 16, 2026: 19.
- **Listed companies:** all 38 cases involve at least one listed company, since that was the entry rule. 36 tickers in total.
- **Latest status of each case:** settled 15, lost by the company 13, won 4, split 3, dismissed 1, withdrawn 1, still pending with only a complaint 1. Many "loss" cases are pending after a lost motion.
- **Outcome by row, from the company's side:** bad 49, good 20, mixed 20.
- **Time from filing to the outcome:** median 605 days for rows that are not complaints.

## How much the stock moved on decision day

- **Moves over 5%** (abnormal, absolute): 8 of 89 rows, 6 after removing the two earnings days.
- **Moves over 10%:** 2, of which 1 is earnings.
- **Moves over 25%:** none.
- **Median absolute abnormal move:** 1.5%. For complaints alone it is 1.3%, for jury verdicts 1.6%, for settlements 2.2%.

**The 10 biggest moves:**

- O-I Glass, FTC noncompete consent order, Jan 4 2023: +17.5%. No news about the order was found, so this move is probably about something else.
- Meta, appeals court upholds dismissal of the states' suit, Apr 27 2023: +11.9%. Earnings the night before; not the ruling.
- Zillow, FTC sues over the Redfin rental-listings deal, Sep 30 2025: -9.5%.
- Alphabet, search remedies ruling (no Chrome sale), Sep 2 2025: +8.6% the next day. The opinion was filed at 4:05 pm, after the close.
- Visa, DOJ debit-card monopoly suit, Sep 24 2024: -6.7%. The suit was reported the evening before.
- Live Nation, DOJ settlement during trial, Mar 9 2026: +5.3%.
- Live Nation, DOJ complaint, May 23 2024: -5.3%. Reported the day before.
- Cigna, Express Scripts FTC insulin settlement, Feb 4 2026: +5.1%. Earnings the next day.
- DaVita, criminal no-poach case survives motion to dismiss, Jan 28 2022: -4.7%.
- Alphabet, DOJ ad-tech complaint, Jan 24 2023: -4.5%.

## Which outcomes can be traded on fast

The aim is an outcome that comes out while the market is open, on a day nobody knew in advance, with the price still moving after it is public. The Liquidia patent order (posted at 11:15 am, company release about 2 hours later, stock -57%) is the model. Antitrust conduct cases produced almost no such events.

- **Outcomes during market hours with no preset date:** 3 of 89 rows. Only 10 rows have any clock time, so the true count is unknown; 79 rows have the date only.
- **Median lead over the company's own release:** 326 minutes, from 1 in-hours row (Alphabet, Aug 5 2024: docket entry 2:42 pm, Alphabet 8-K 8:08 pm). After the Sep 2 2025 remedies ruling, Alphabet's 8-K came 1,465 minutes later, but that ruling was after the close. Every company release time in the CSV is from an 8-K whose item text was read and is about the event; 4 matched 8-Ks were about something else (a share offering, a credit deal, an acquisition) and were left blank.
- **Median minutes to half the move:** 1 minute, from 1 row (Meta, Nov 18 2025), where the whole move was 0.1%. Minute bars from Polygon only reach back two years, and only 1 minute-timed, in-hours outcome falls inside that window.
- **Why so few:** big antitrust outcomes are covered live by the press, settlements are usually leaked a day early, and jury verdicts come at the end of a scheduled trial.

**All in-hours outcomes found (fewer than ten exist in this list):**

- Alphabet, search monopoly liability ruling, Aug 5 2024, docket entry 2:42 pm, not scheduled: -1.5% (a market-wide sell-off day).
- Meta, FTC monopoly ruling for Meta, Nov 18 2025, docket entry 12:43 pm, not scheduled: +0.1%. Half the move was done in 1 minute.
- Alphabet, ad-tech remedies ruling (no breakup), Sep 2 2026, first news by 2:53 pm, not scheduled: +0.7% over two days.
- Live Nation, jury verdict for the states, Apr 15 2026, first news by 3:53 pm, scheduled trial: -4.5% over two days.
- **Before the open, from the company itself:** the Zillow and Redfin settlement with the FTC was signed on Saturday Aug 22 2026 and first appeared in Zillow's 8-K at 9:04 am on Monday Aug 24, before the market opened. Zillow +0.6% and Rocket Companies (Redfin's owner) +2.6% over two days.
- **After the close, not scheduled:** Alphabet search remedies ruling, Sep 2 2025, 4:05 pm, +8.6% next day. This is the best fast-reaction example in the list, but it had to be traded after hours.

## Files

- `scripts/universe_antitrust_conduct.py`: the hand-checked case and event list plus the price, SEC and Polygon joins. Raw downloads are cached in `data/universe/antitrust_conduct/raw/` (175 MB, not committed).
- `data/universe/antitrust_conduct/cases.csv`: one row per event per listed company.

This is historical research, not investment advice.
