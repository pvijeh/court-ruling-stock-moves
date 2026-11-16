# Government lawsuits to block mergers, 2021 to October 2026: every case, and how the stocks moved

**Summary**

- **What this is:** a list of every lawsuit a US government agency filed between 2021-01-01 and 2026-10-14 to stop a merger in which the buyer or the target trades on a US stock exchange, with each company's stock move on the day the suit was filed and on the day the case was decided.
- **Why it matters:** the earlier study in this repo (`data/lawsuit_moves_reviewed.csv`) picked 40 dramatic rulings by hand. To estimate, on the day a suit is filed, how much a stock will move when the case ends, the list has to include the cases where nothing happened.
- **What we found:** 32 cases (30 different deals; the Kroger/Albertsons deal was fought in three courts), 48 company rows. Half the measured decision-day moves were smaller than 4.1%. Targets of all-cash deals moved most: Surmodics +51% and Capri -49%.
- **Speed:** one outcome is known to have come out while the market was open: the Kroger/Albertsons ruling of 2024-12-10, which first hit the stocks at 3:21 pm Eastern. Half of the move to the close came within 2 minutes. Times to the minute exist only for the 5 cases checked against 1-minute prices and CourtListener; the other rows have only a date.
- **Still open:** 8 companies have no usable free daily price history, so their moves are blank: 7 delisted targets (Change Healthcare, Spirit Airlines, Aerojet Rocketdyne, Activision Blizzard, Black Knight, Horizon Therapeutics, TEGNA) and Paramount Global, whose old ticker PARA returns wrong prices on Yahoo. No row has been checked against the court's own opinion PDF yet, so none is marked high confidence.

**Terms used below**

- **Merger challenge:** a lawsuit or administrative complaint by a government agency asking to block or undo a merger or acquisition.
- **DOJ:** the Antitrust Division of the US Department of Justice. It sues in federal district court.
- **FTC:** the Federal Trade Commission. It can ask a federal judge for a **preliminary injunction** (a court order that stops the deal from closing until the FTC's own trial is over), and it can file a **Part 3 complaint**, which starts a trial inside the FTC before an agency judge.
- **State attorney general (AG):** a state's top lawyer; states can sue to block a merger on their own.
- **Consent decree / consent order:** a settlement in which the agency drops its challenge and the companies agree to conditions, usually selling off part of the business (a **divestiture**).
- **Acquirer / target:** the buyer and the company being bought.
- **Abnormal return:** the stock's percentage change minus the change in a benchmark fund over the same days. The benchmark is SPY (the S&P 500 fund), or XBI (a biotech fund) for drug companies.
- **Decision day:** the first trading day on which the outcome could be priced. A ruling published after 4:00 pm Eastern or on a weekend counts on the next trading day. When the publication time is unknown, the move is measured over two days (the decision day and the next one), and the row says so.
- **Deal spread:** the gap between the cash price the buyer agreed to pay and the target's market price. A wide spread means the market doubts the deal will close.

## What was counted

**Included**

- Every complaint filed 2021-01-01 to 2026-10-14 by the DOJ, the FTC (federal court or Part 3) or a state AG to block or undo a merger or acquisition, where the buyer, the target or the target's listed parent trades in the US.
- Cases that ended in a settlement, a dismissal, a court ruling, or the companies walking away.
- One case without a complaint: TransDigm dropped its $960M purchase of Stellant Systems in July 2026 after the DOJ said publicly that it would sue. It is marked low confidence.

**Left out**

- Settlements filed on the same day as the complaint, where the agency never actually tried to stop the deal (for example S&P Global/IHS Markit, Danfoss/Eaton, Republic Services/Santek). The DOJ's listing has 13 of these from 2021 to early 2025.
- Deals dropped during an investigation without a public announcement that the agency would sue.
- Challenges where no party is US-listed (for example US Sugar/Imperial Sugar, Novant-only hospital deals).
- Suits that are not about a merger, even when they involve the same companies (the DOJ's suit against the American Airlines/JetBlue partnership, Live Nation).

**Where the cases came from**

- The FTC's case library, filtered to merger cases: 496 case pages, 73 updated since 2021. ftc.gov refuses plain scripts, so pages were read through a normal Chrome browser on this machine.
- The DOJ's "Antitrust Case Filings" list, filtered to civil merger cases: 24 cases opened up to February 2025. justice.gov refuses both scripts and the browser here, so the list was read from the Internet Archive's saved copies. The archive has no filtered copy after February 2025, so DOJ cases since then (HPE/Juniper) come from news and company filings.
- State AG suits came from news searches and the AGs' press releases.
- Each case's dates, deal terms and outcome were then taken from the agency press release, news coverage and the companies' 8-K filings (the form a US-listed company files with the SEC to report a major event). The source links are in the `sources` and `decision_source_url` columns. `docket_url` points to the agency's case page, which lists the court filings, except for the 5 cases checked on CourtListener, where it points to the court docket there.
- CourtListener (a free site that copies federal court dockets) was used for 5 searches only, because its free quota is shared with other sessions. They found the time of the decision for the 5 fast-trade candidates below. The responses are cached in `raw/cl/`.

**How complete it is**

- The FTC and DOJ lists are the agencies' own; every litigated merger case on them from 2021 on with a US-listed party is in the file.
- State AG suits have no central list. A state suit filed alongside a federal one is folded into that case's notes; the three filed separately (Washington and Colorado against Kroger/Albertsons, eight states against Nexstar/TEGNA, twelve states against Paramount Skydance/Warner Bros. Discovery) are their own cases. A small state suit with little news coverage could be missing.
- DOJ cases filed after February 2025 rely on news, not the DOJ's list.

## Counts

**Cases by year the complaint was filed**

- 2021: 4
- 2022: 7
- 2023: 6
- 2024: 7 (3 of them are the Kroger/Albertsons deal in three courts)
- 2025: 5
- 2026 (to October 14): 3

The prompt guessed 10 to 30 a year; the real number of litigated challenges with a listed party is 4 to 7.

**Listed companies**

- 32 cases, 48 company rows, 43 different tickers.
- 16 cases have both the buyer and the target listed (two rows each); 16 have only one listed side.

**Outcomes (per case)**

- Agency won in court (`loss` for the companies): 8. Examples: JetBlue/Spirit, Tapestry/Capri, Kroger/Albertsons, Edwards/JenaValve, Nexstar/TEGNA (a preliminary injunction; Nexstar has appealed, so the fight is not over).
- Companies won in court (`win`): 8. Examples: Microsoft/Activision, UnitedHealth/Change, Meta/Within, Tempur Sealy/Mattress Firm, GTCR/Surmodics.
- Deal dropped (`withdrawn`): 8. Examples: Nvidia/Arm, Lockheed/Aerojet, Aon/Willis Towers Watson.
- Settled with conditions (`settled`): 7. Examples: UnitedHealth/Amedisys, HPE/Juniper, Amgen/Horizon, ICE/Black Knight.
- Agency dropped the case (`dismissed`): 1, Amex GBT/CWT.
- Still pending with no first decision: 0.

From each company's side, 24 rows were good outcomes, 23 bad and 1 unknown (TEGNA, which had already been bought when the injunction came).

## How the stocks moved

**On the decision day** (40 of 48 rows have prices)

- Moved more than 5% (abnormal, either direction): 15
- More than 10%: 6
- More than 25%: 2
- Median absolute abnormal move: 4.1%. Buyers 3.1% (27 rows), targets 4.2% (13 rows).

**On the filing day** (41 rows have prices): median absolute abnormal move 2.7%; 9 rows moved more than 5%.

**The 10 biggest decision-day moves (abnormal)**

- Surmodics (target), +51.0%: judge refused to block GTCR's $43-a-share purchase, 2025-11-10. The stock was $31.02 the day before the complaint.
- Capri (target), -49.3%: judge blocked Tapestry's $57-a-share purchase, 2024-10-24. The stock was $38.53 the day before the complaint.
- Meta (buyer), +24.2%: judge refused to block the Within purchase, 2023-02-01. The move is almost all Meta's earnings report the same evening, not the ruling; the row is flagged.
- Tapestry (buyer), +15.8%: same ruling as Capri. Tapestry's investors were glad the deal was off.
- Aon (buyer), +11.9%: Aon and Willis Towers Watson dropped their deal, 2021-07-26.
- HPE (buyer), +10.8%: settled with the DOJ on Saturday 2025-06-28, a week before trial.
- Warner Bros. Discovery (target), +9.4%: settled with twelve states, 2026-09-21.
- Willis Towers Watson (target), -8.8%: same event as Aon.
- Juniper (target), +8.1%: same settlement as HPE.
- Spectrum Brands (seller of its hardware unit), +5.8%: settled with the DOJ mid-trial, 2023-05-05.

All ten were measured over two days (the decision day plus the next), because the ruling time is either unknown or only inferred from prices (see the next section).

## Which outcomes can be traded on fast

The question: how many outcomes were published while the market was open (9:30 am to 4:00 pm Eastern), on a day nobody knew in advance, so a fast alert could beat the price?

**How the times were found**

- None of the 32 decision dates was announced in advance (none was a jury verdict), so every case passes the date test. The time of day is the hard part.
- For the 5 cases most likely to pass (unscheduled, with a big or unexplained move), two sources were checked:
  - **First price jump:** Polygon's 1-minute stock prices (free history goes back about 2 years) on the decision day and the next day, including trading before 9:30 am and after 4:00 pm. The jump is the first minute that moved the stock at least 2%, and at least 30% of its two-day move, in the direction of that move, and held for the next 3 minutes. That is the latest the news could have been out; it may have come out a few minutes earlier. These rows say `inferred from price` in `time_precision`.
  - **CourtListener time:** when CourtListener first recorded the court's docket entry (a docket is the court's running list of filings). The court may have posted it earlier, so this is also a latest-possible time.
- The earlier of the two goes in `first_public_time_et`. Both are in `notes`.
- The other 43 rows have only a date from news reports, or an 8-K time on a day when an untimed news story was already out. Of all 48 rows, 20 are known to have come out outside market hours and 26 are unknown.

**Results**

- **Came out during market hours with no preset date: 1 case, 2 rows (Kroger and Albertsons).**
- **Median lead over the company's own release: 1,358 minutes (about 22.6 hours), over 4 rows.** This compares against the time the SEC accepted the company's 8-K. A company press release on a newswire may have come earlier; that was not checked.
- **Median minutes to half the move: 1, over 5 rows.** This is the time from the first public moment until the stock had made half of its move to the close of the session that priced the news. The price adjusted almost at once every time.
- **Best examples:** only these 5 cases have times to the minute, so there is no top 10.

**The 5 cases, earliest time first in each**

- **Kroger/Albertsons (FTC suit in Oregon federal court), 2024-12-10:** Albertsons fell 4.4% in the minute ending 3:21 pm, from $19.12 to $18.28. Kroger rose. Half the move to the close took under a minute for Albertsons and 2 minutes for Kroger. CourtListener did not record the opinion until 5:09 pm, so the news was out about 2 hours before CourtListener had it. What put it out first is not known. Albertsons' 8-K came the next day at 1:31 pm, Kroger's at 10:18 pm.
- **Tapestry/Capri, 2024-10-24:** Capri fell from $41.61 to $35 at 4:02 pm, two minutes after the close, in after-hours trading (trading after 4:00 pm, when few shares change hands). CourtListener recorded the opinion at 4:08 pm. Half the move took 1 minute for Capri and 4 minutes for Tapestry. Outside market hours.
- **GTCR/Surmodics, 2025-11-10:** the judge ruled by phone, so only the lawyers on the call heard it. The docket's minute entry (a short note of what happened at a hearing) reached CourtListener the next day at 11:15 am. But Surmodics had already jumped at 7:10 am that morning, before the open, and made half its move within a minute. Surmodics' 8-K came on 2025-11-12 at 6:15 am. Outside market hours.
- **Edwards/JenaValve, Friday 2026-01-09:** CourtListener recorded the sealed opinion at 4:24 pm, 24 minutes after the close. Edwards' 8-K came at 11:51 pm, 447 minutes later. The stock moved only -2.7% against the S&P 500 fund on the next trading day, with no sharp jump, which fits a ruling after the close.
- **Nexstar/TEGNA, 2026-04-17:** CourtListener recorded the order at 8:43 pm. Nexstar rose 2.5% against the S&P 500 fund on the next trading day, with no sharp jump. No company release time was found.

**What this means**

- In the one ruling that came out during trading, the price made half its move within 2 minutes. In the Liquidia patent case the press release came about 2 hours after the order; here the companies' 8-Ks came about a day later. But the market did not wait for them. An alert would have to fire within a minute or two to beat the price.
- CourtListener was behind the market in all three cases where both times exist: by 6 minutes (Capri), about 2 hours (Kroger/Albertsons) and about 4 hours (Surmodics). Watching CourtListener alone would have been too slow.

## Data gaps

- **No prices** for 7 delisted targets: Change Healthcare, Spirit Airlines, Aerojet Rocketdyne, Activision Blizzard, Black Knight and Horizon Therapeutics (Yahoo dropped them, and Polygon's free plan only goes back two years); TEGNA was delisted before its decision. Their deal prices are in `notes`. Paramount Global (PARA, the seller of Simon & Schuster) is also blank: Yahoo's PARA history shows closes near $97,800, so it is not Paramount's.
- **Prices from Polygon instead of Yahoo** for Amedisys, Juniper, Surmodics, Amex GBT, Paramount Skydance and Warner Bros. Discovery (Yahoo had no or only a few bars). These are not adjusted for dividends.
- **Market cap** is blank for the 8 companies without prices, Meta (no share count in its XBRL data for that date), Sanofi (files in euros), and Zillow and Rocket (no share count found for the filing date).
- **Product revenue at issue** is not filled. `revenue_at_stake_usd` is the deal value for buyers, as the brief asked; no 10-K breaks out the overlapping product line for these deals.
- **Option-implied moves** are blank: there is no free history for expired option contracts.
- **Confidence:** 47 rows are medium (case, company and outcome checked against the agency's press release and news, not against the opinion PDF) and 1 is low (TransDigm, no complaint filed).

## How to rebuild

- `python3 scripts/universe_merger_challenge.py sources` re-reads the FTC and DOJ listings into `data/universe/merger_challenge/raw/` (needs Chrome on port 29229 for ftc.gov).
- `python3 scripts/universe_merger_challenge.py build` writes `cases.csv` from the hand-checked case list in the script, Yahoo or Polygon prices, SEC filings and Google News dates.
- `python3 scripts/universe_merger_challenge.py stats` prints every number in this document.
- Downloads are cached in `raw/` (about 125 MB, not committed).

This is historical research, not investment advice.
