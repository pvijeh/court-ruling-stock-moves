# Large jury verdicts against or won by US-listed companies, 2021 to October 2026

## Summary

- **What this is:** a list of every large US jury verdict we could find from 1 January 2021 to 14 October 2026 where a company with US-traded stock was the plaintiff (the side suing) or the defendant (the side being sued). A jury verdict is the jury's decision at the end of a trial, including how much money one side owes the other.
- **Why it matters:** the aim is to estimate, before a case is decided, how much a company's stock is likely to move when it is. An earlier study picked 40 dramatic rulings by hand. That sample overstates the typical move, because quiet outcomes were left out. This list keeps the quiet ones.
- **What counts:** a verdict of at least $100 million, or at least 2% of the company's stock-market value (market cap) the day before the verdict, so small companies are included too.
- **What we found:** 117 verdicts and 132 company rows (a verdict between two listed companies gets one row per company), covering 96 different stocks.
- **The headline:** most verdicts barely moved the stock. The typical (median) move against the market was 1.4%. Only 6 of 108 priced rows moved more than 10%, mostly smaller companies where the award was a large share of the company's value. Illumina Inc.'s 21% move came on the same two days as its quarterly results.
- **On speed:** jury verdicts are poor material for a fast-alert strategy. The trial date is public, the verdict is read aloud in a courtroom, and no free source records the minute it happened. The better targets are the judges' and appeals courts' later rulings that cut or erase verdicts, which arrive on unannounced days.
- **Still open:** filing dates, trial start and end dates, and court docket numbers are blank for most rows. Prices are missing for some over-the-counter and delisted stocks. See "What is missing".

## How the list was built

- **No official register exists.** US courts do not publish a free list of verdicts. So we combined several free sources and checked each case by hand.
- **Year-end lists:** TopVerdict publishes the 100 largest verdicts each year and the largest by category (patent, product liability and so on). We read the 2021 to 2025 lists, about 670 entries, and matched the defendants and plaintiffs to listed companies.
- **Company filings:** listed companies must tell investors about material lawsuits. We ran SEC full-text searches of 8-K (current event), 10-Q and 10-K (quarterly and annual) filings for phrases like "jury verdict" and "jury awarded", which returned about 4,800 filings, and read the passages that named a verdict amount.
- **News:** Google News searches confirmed each verdict's date, amount and parties, and found later events such as appeals.
- **CourtListener:** the free court-records site was not used in the end. Its free quota (about 125 requests a day) is shared with other projects and was used up during this build, so no row depends on it, and docket numbers and filing dates are still blank.
- **Hand check:** every row was matched to at least one dated report of the verdict itself. Rows marked high confidence also match the company's own SEC filing. Medium means news reports agree but the court record itself was not read. Low means a key detail, such as the exact day or the court, is still unconfirmed.

## How stock moves were measured

- **Return:** the percentage change in the closing price from one trading day to the next.
- **Abnormal return:** the stock's return minus the return of the overall market on the same days, measured by the SPY index fund, or the XBI biotech fund for drug companies. This strips out moves that had nothing to do with the case.
- **Two-day window:** a verdict can come in the morning, the afternoon or after the market closes, and the free reports almost never say which. So the decision-day move is the two-day move covering the verdict day and the next trading day.
- **Prices:** daily closes come from the Nasdaq public quote API and Polygon, because Yahoo Finance was refusing requests from this machine during the build. Nasdaq closes adjust for stock splits but not dividends, which adds a small error on the few days a dividend is paid.

## Counts

**Verdicts per year**

- 2021: 12
- 2022: 21
- 2023: 18
- 2024: 35
- 2025: 21
- 2026: 10 (to mid-October)

**Who was on which side**

- Listed company was the defendant: 103 rows.
- Listed company was the plaintiff: 29 rows.
- Verdicts under $100 million that qualify only because they were at least 2% of the company's value: 17 rows.
- Rows where the award was at least 2% of market cap: 29.

**Outcomes**

- Good for the listed company: 29 rows. Bad: 101. Mixed: 2.
- By the case's current status: loss 97, settled 6, win 29. "Loss" means the company lost at trial; "settled" means the parties settled after the verdict.
- Many large awards were later cut or thrown out by the trial judge or an appeals court. These later events are in each row's notes with dates.

## How much the stock moved

- **Rows with a measured move:** 108 of 132.
- **Moved more than 5% against the market:** 13.
- **More than 10%:** 6.
- **More than 25%:** 2.
- **Median absolute abnormal move:** 1.4%. Half the rows moved less than this, in either direction.

**The 10 biggest moves**

- **Sotera Health Co. (SHC), 2022-09-19:** -44.0%. Kamuda v. Sterigenics U.S.; defendant; $363M, 9% of market cap.
- **Appian Corp. (APPN), 2022-05-09:** +28.4%. Appian Corp. v. Pegasystems Inc.; plaintiff; $2,036M.
- **Pegasystems Inc. (PEGA), 2022-05-09:** -20.8%. Appian Corp. v. Pegasystems Inc.; defendant; $2,036M, 73% of market cap.
- **Illumina Inc. (ILMN), 2022-05-06:** -20.6%. Complete Genomics v. Illumina; defendant; $334M, 1% of market cap. Earnings came out in the same window, so this is not the verdict alone.
- **Puma Biotechnology (PBYI), 2024-05-16:** -10.4%. Puma Biotechnology and Wyeth v. AstraZeneca (Tagrisso); plaintiff; $108M, 48% of market cap.
- **CareDx Inc. (CDNA), 2024-01-26:** -10.1%. Natera v. CareDx; defendant; $96M, 16% of market cap.
- **Alphabet Inc. (GOOGL), 2025-09-03:** +8.5%. Rodriguez v. Google (Web & App Activity); defendant; $426M.
- **Caesarstone Ltd. (CSTE), 2024-08-06:** -7.7%. Gomez (silicosis) v. Caesarstone et al.; defendant; $52M, 29% of market cap.
- **Western Digital Corp. (WDC), 2024-07-29:** -7.0%. MR Technologies v. Western Digital; defendant; $262M, 2% of market cap.
- **Ramaco Resources (METC), 2026-09-28:** -6.2%. Ramaco Resources v. Chubb (insurance); plaintiff; $30M.

The pattern is plain. Big companies shrug off even billion-dollar verdicts, because investors expect appeals to cut them and the sums are small next to the company's value. Intel lost $2.18 billion in 2021 and fell about 3% against the market. The large moves came where the award was a big slice of a small company.

## Which outcomes can be traded on fast

The model case for this project is Liquidia: a court posted an order at 11:15 a.m., during market hours, on a day nobody knew in advance, and the company's own press release came about two hours later. The question is how many cases in this list look like that.

- **Published during market hours with no preset date:** 0. Every row here is a jury verdict at the end of a trial whose start date was public, so none qualifies as unscheduled. The day of the verdict is uncertain, but only within a trial window everyone can see.
- **Exact time of the verdict:** found for 0 rows. Verdicts are read aloud in court. The first public source is the courtroom, then reporters (Law360, Reuters, Bloomberg Law). The free news feeds give only the day, so time precision is "day" throughout.
- **Median lead over the company's own release:** not measurable. This needs a minute-level time for both the verdict and the company's release; we have the second but not the first.
- **Median minutes to half the move:** not measurable. This needs both the minute of the news and one-minute price bars. Polygon's free plan has those bars for about the last two years, which covers 41 rows, but without a news time there is no starting point.
- **Company releases:** 27 rows have an 8-K filing about the verdict, timed from EDGAR's acceptance stamp. 9 of those were filed while the market was open; most came after the close or days later.

**The 10 best examples**

The rulings that fit the Liquidia pattern are not the verdicts themselves but what judges and appeals courts did to them afterwards. A judge can rule on a post-trial motion any day, and appeals courts post opinions without notice. Below are the ten largest stock moves around those rulings, measured as the two-day abnormal move covering the day of the first report and the day before. The time of day was not found in free sources, so these are candidates for a live alert, not proven fast trades.

- **PEGA, 2024-07-30:** Virginia Court of Appeals reverses the $2.04B Appian verdict. Abnormal move +6.2%. Source: Holland & Knight 2024-08-05.
- **GEN, 2026-03-11:** Federal Circuit reverses the Columbia patent judgment. Abnormal move -5.5%. Source: IPWatchdog 2026-03-11.
- **INTC, 2023-12-04:** Federal Circuit vacates the $2.18B VLSI damages award. Abnormal move -5.3%. Source: Reuters 2023-12-04.
- **PEGA, 2025-03-07:** Virginia Supreme Court agrees to hear Appian's appeal. Abnormal move -3.0%. Source: PR Newswire 2025-03-07.
- **UPS, 2024-11-18:** judge cuts the $238M Gratton verdict by nearly $200M. Abnormal move +2.8%. Source: New York Post 2024-11-18.
- **AAPL, 2026-07-21:** judge denies Apple's bid to overturn the $634M Masimo verdict. Abnormal move -2.5%. Source: 9to5Mac 2026-07-21.
- **CVX, 2026-04-17:** US Supreme Court sends the Plaquemines case to federal court. Abnormal move -2.0%. Source: NOLA.com 2026-04-17.
- **APPN, 2024-07-30:** Virginia Court of Appeals reverses the $2.04B Appian verdict. Abnormal move -1.5%. Source: Holland & Knight 2024-08-05.
- **T, 2025-09-24:** Federal Circuit overturns the $166M Finesse verdict. Abnormal move -1.2%. Source: Reuters 2025-09-24.
- **VZ, 2024-10-01:** judge orders a new trial on the $847M patent verdict. Abnormal move +1.2%. Source: Reuters 2024-10-01.

Most of these moves are small, and several go the wrong way: Intel fell when its $2.18 billion loss was thrown out, and Gen Digital fell when its judgment was reversed. Over two days, other news drowns out a ruling that a big company had already priced in. The clearest case is Pegasystems, a mid-sized company facing a verdict worth about 70% of its value, which rose 6.2% against the market when the appeals court threw the verdict out. That is the profile worth an alert: a pending post-trial or appeal ruling on an award that is large next to the company.

## What is missing

- **Verdicts we probably missed:** the TopVerdict lists stop at about 100 verdicts a year, and 2026 has no list yet, so 2026 relies on company filings and news. Our rough estimate, not a measurement, is that we have 80 to 90% of verdicts over $100 million and perhaps half of the smaller ones that qualify only under the 2% rule. Those smaller cases rarely make year-end lists, and small companies do not always file an 8-K.
- **Who counts as listed:** verdicts against private subsidiaries are booked to the listed parent (Monsanto to Bayer, Philip Morris USA to Altria). Bayer, Fannie Mae, Freddie Mac and Netlist trade over the counter rather than on an exchange; they are kept but most have no free price history.
- **Missing prices:** 24 rows have no measured move, mostly over-the-counter stocks, delisted stocks, and stocks the Nasdaq quote API does not carry.
- **Facts at filing:** the date each lawsuit was filed, the trial dates and the docket numbers are blank for most rows. Collecting them needs about two pages of court records per case, which the shared CourtListener quota does not allow in one session. Market cap at filing is therefore blank; the notes give market cap the day before the verdict instead.
- **Defense verdicts left out:** this list counts awards of money. Trials where the company won outright, so that no money was awarded, are not here, though they move stocks too.
- **Option prices:** the market's expected move before a verdict (from option prices) is blank. Free historical option data mostly does not exist for these dates.

## Bottom line

For most listed companies a jury verdict, even a huge one, is a non-event for the stock. The verdicts that matter are the ones that are large relative to a small company, and the later rulings that cut or erase them. If Peter wants a fast alert, the better place to look is post-trial and appeals rulings in cases already on this list, not the verdicts themselves.

_This is historical research, not investment advice. Rows marked medium or low confidence have not been checked against the court record._
