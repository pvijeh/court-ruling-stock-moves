# Section 337 import-ban cases, 2021 to 2026-10-14: the complete list

This is historical research, not investment advice. Anything estimated is marked as estimated.

- **What this is:** every US International Trade Commission (ITC) Section 337 investigation that was open, started or decided between 2021-01-01 and 2026-10-14, with one row for each US-listed company involved. A Section 337 case is a patent or trade-secret fight at the ITC where the prize is an exclusion order: a ban on importing the accused product into the US.
- **Why it matters:** the earlier 40-case study in this repo picked dramatic rulings. To estimate, at filing, how much a stock will move when a case is decided, we need the boring cases too: settlements, withdrawals and cases still running.
- **Where we looked:** the ITC's own public investigation database, every ITC Section 337 notice in the Federal Register, SEC filings, and free daily and one-minute stock prices.
- **What we found:** 358 investigations, 211 of them with a US-listed party, 385 company rows. Most end in settlement or withdrawal. On the 297 decision days we could price, the median abnormal move was 1.7%; 41 rows moved more than 5% and 1 more than 25% (Traeger, on the day of its earnings release).
- **Still open:** the ITC's document system (EDIS) shows posting times only after a login, so no row has a minute-level publication time, and the speed questions can only be answered roughly from one-minute prices for the last two years.

## What was counted

**The universe.** An investigation is in the list if it is a Section 337 violation investigation (not an enforcement, advisory or modification side-proceeding) and it has any date on or after 2021-01-01 (complaint, institution, judge's decision, Commission decision or termination), or it is still open. That gives 358 investigations. Some were started in 2019 or 2020 and decided after 2021; 15 have no institution date because the ITC has not yet started them, declined to start them, or the complaint was withdrawn first.

**The parties.** The complainant is the company that files and asks for the import ban. Respondents are the companies accused. A row is written for each US-listed company on either side, so a case between two listed companies has two rows. Subsidiaries are grouped under their listed parent (Google LLC and Fitbit under Alphabet, Ethicon under Johnson & Johnson). Names were matched to tickers with a hand-written list of about 190 companies in `scripts/universe_itc337.py`, including renamed and acquired companies (Juniper into HPE, VIZIO into Walmart, Velodyne into Ouster, CommScope renamed Vistance Networks). Foreign companies count when their shares or ADRs (American depositary receipts, foreign shares traded in New York) are listed in the US; Samsung and LG Electronics are not, LG Display is.

**The events.** For each investigation the list records the complaint date, the institution date (when the ITC formally starts the case), the evidentiary hearing (the ITC's trial, before an administrative law judge), the judge's initial determination (ID), the Commission's final determination (FD), any exclusion or cease-and-desist orders, the end of presidential review (60 days after a violation finding, computed, not looked up), and terminations by settlement, consent order or withdrawal.

**The decision date.** For each row `decision_date` is the most material event for that company: the Commission's final determination where there is one; otherwise the date the company left the case (settlement, consent order, withdrawal); for open cases with a judge's final ID, the ID date. Open cases with no ID have a blank decision date and outcome `pending` (70 rows). All other dates are in `notes`.

## How complete the list is

**Investigations: very close to complete.** The ITC database lists 51 investigations started in 2021, 60 in 2022, 36 in 2023, 45 in 2024, 43 in 2025 and 54 in 2026 so far. As a cross-check, the Federal Register published an "Institution of Investigation" notice for 50, 57, 35, 44, 41 and 55 in those years. Every investigation with such a notice is in our list except one: 337-TA-1273, which has a Federal Register notice but no record in the ITC database.

**Companies: probably complete for well-known names, weaker for small ones.** A listed company is missed if its subsidiary's name is not on the matching list. We checked every matched name by eye and removed one false match (Amtech Systems LLC, a private RFID maker, is not Amtech Systems Inc.). We did not check the roughly 2,500 unmatched party names one by one; most are Chinese and other non-US manufacturers and private US firms.

**Outcomes.** Outcomes come from the ITC database's disposition field for each respondent and the Commission's decision type. Each row was then checked automatically against the Federal Register notices for the case: does a notice name the company, and does its wording match the outcome? 316 rows passed (confidence `medium`), 58 did not (`low`). 11 rows were read by hand against the notices and are `high`. The automatic check is not a hand check, and the earlier study found that automatic matching was wrong in about half of its cases, so treat `medium` with care.

## Counts

**Investigations by year started (ITC database).**
- 2019: 14 and 2020: 39 (still open or decided after 2021-01-01)
- 2021: 51
- 2022: 60
- 2023: 36
- 2024: 45
- 2025: 43
- 2026 to 2026-10-14: 54

**How many involved a listed company.** 211 of 358 investigations (59%). They produce 385 rows across 186 tickers: 117 rows where the listed company is the complainant and 268 where it is a respondent. 91 investigations have more than one listed company.

**Status of the 358 investigations.** 272 terminated, 55 still before the judge, 15 before the Commission, 7 withdrawn before institution, 4 not instituted, 4 waiting to be instituted, 1 sent back to the judge.

**Outcome split, by company row.** The outcome is from the case's point of view: `win` means the complainant got a violation finding, `loss` means it did not.
- Settled: 135
- Pending: 74
- Won (violation found; the respondent rows for these are `loss`): 71
- Withdrawn: 55
- Lost: 34
- Dismissed: 14
- Split (violation as to some respondents, not others): 2

From the listed company's side (`outcome_for_company`): 134 good, 37 bad, 2 mixed and 212 unknown. Settlements and withdrawals are `unknown` because the terms are almost never public.

**Was the date known in advance?** 58 rows have a final determination issued on the Commission's public target date, the deadline the ITC sets and publishes, so the market knew which day to watch. 257 rows are settlements, withdrawals or decisions on a day nobody announced. The other 70 have no decision yet.

## How much the stock moved

**Definitions.** A return is the close-to-close change in the share price. The abnormal return is the stock's return minus the return of a benchmark that day, which removes market-wide moves: the S&P 500 fund SPY, or the biotech fund XBI for drug companies. The ITC posts documents during the day but we do not know at what minute, so each event return covers two trading days: the event day and the next one.

**Coverage.** 297 of the 315 decided rows have a decision-day return. The 18 without are companies that were bought or delisted, so the free price sources no longer carry them (Velodyne, VIZIO, Hologic, Juniper, Skechers, Qurate, CommScope, DISH, iRobot, Masimo and others), plus SharkNinja, which listed only after its 2023 decision. Market capitalisation at filing is filled for 297 rows and filing-day returns for 348. Daily prices come from Yahoo (368 rows) and Polygon (10 rows).

**Size of moves (abnormal, two-day decision window, 297 rows).**
- Moved more than 5%: 41
- More than 10%: 10
- More than 25%: 1
- Median absolute move: 1.7%

23 of the 297 rows had an earnings release (an 8-K with Item 2.02) within a few days of the decision. Without them: 30 of 275 moved more than 5%, 7 more than 10%, none more than 25%, median 1.5%. For a company like Apple or Qualcomm, an ITC result is small next to earnings and market noise, so many of the moves below are probably not caused by the case.

**The 10 biggest moves.**
- **Traeger (COOK), 337-TA-1237, 2022-05-12:** +27.9%. Violation found against GMG Products on the target date. Traeger filed its earnings 8-K at 20:07 ET the evening before, so earnings is the likelier cause.
- **Shoals Technologies (SHLS), 337-TA-1365, 2025-01-14:** -24.4%. The Commission found no violation, reversing the judge, one day before its target date. Hand-checked.
- **GoPro (GPRO), 337-TA-1400, 2026-02-26:** +16.3%. Violation found against Insta360, on the target date. Hand-checked.
- **Ouster (OUST), 337-TA-1322, 2023-01-09:** +14.0% when Velodyne's case against it ended. Ouster and Velodyne had announced a merger in November 2022 (from memory of news reports, not checked here), so the end of the case was likely expected. Not hand-checked.
- **Arlo (ARLO), 337-TA-1242, 2021-11-10:** +12.2%. The Commission found no violation, but Arlo had reported earnings the evening before, so earnings is the likelier cause.
- **Nokia (NOK), 337-TA-1380, 2025-04-23:** -11.6%. Case against Amazon and HP ended by settlement. Most of the move was before the open on 2025-04-24, the day Nokia reported quarterly results (a 6-K, which our 8-K earnings check does not catch), so it is probably earnings.
- **Shoals Technologies (SHLS), 337-TA-1438, 2026-06-25:** -11.2%, even though Shoals won an exclusion order against Voltage on the target date. Hand-checked; the cause of the fall is not known.
- **Beauty Health (SKIN), 337-TA-1416, 2025-03-11:** +10.8% around the withdrawal of its case against clinics. Beauty Health reported earnings on the evening of 2025-03-12, inside the window, so the case is probably not the cause.
- **Qualcomm (QCOM), 337-TA-1450, 2026-05-12:** -10.7% on a settlement with Onesta IP. Half the move was done by 09:34 ET, which points to other news before the open.
- **T1 Energy (TE), 337-TA-1422, 2026-02-10:** -10.1% when its solar case against Canadian Solar and Adani ended on a joint motion.

## Which outcomes can be traded on fast

The goal is outcomes that become public while the market is open (9:30 to 16:00 ET) on a day nobody scheduled, so an alert can beat the company's own press release.

**How many came out during market hours with no preset date: unknown at the minute level.** 257 rows had no preset date. The ITC posts orders and notices in EDIS, its document system, and the time of posting is only shown after logging in, which we did not do. The Federal Register copy comes days later. So every row has `time_precision` = `day` and `during_market_hours` = `unknown`.

**A stand-in from minute prices.** For 53 rows we have Polygon one-minute bars for the day of the bigger move. We measured when the stock had covered half of that day's move. In 18 rows half the move happened between 09:45 and 16:00 ET, which suggests news during the session; in the other 35 the stock had already moved by the open, which suggests news overnight or before 09:30. 16 of the 18 are unscheduled settlements or withdrawals. This is an estimate of when the market reacted, not of when the ITC posted.

**Median lead over the company's own release: not measurable.** We searched SEC full-text search for each company's 8-K or 6-K that mentions the ITC near the decision. Only 2 turned up: Masimo filed at 21:57 ET on the day of its 2023-10-26 win over Apple, after the close, and Altria filed at 12:03 ET the day after a 2025-01-29 decision. Large companies rarely file an 8-K for an ITC result. With no minute-level publication time, `lead_minutes_vs_company_release` is blank.

**Median minutes to half the move: not measurable.** `minutes_to_half_move` needs a minute-level publication time to start the clock, so it is blank. The clock time of the half-way point is in `notes` for the 53 rows with minute bars.

**The 10 best examples (unscheduled, half the move during the session, no earnings release nearby, by size of abnormal move).** None is hand-checked for cause.
- T1 Energy, 337-TA-1422, 2026-02-10: -10.1%, half the move by 10:05 ET
- Apple, 337-TA-1443 (settled with Longitude Licensing), 2026-07-15: +6.0%, by 09:45
- Super Micro Computer, 337-TA-1465 (Adeia withdrew), 2026-04-27: -6.0%, by 10:15
- Perrigo, 337-TA-1498, 2026-09-09: -5.7%, by 11:38
- Hewlett Packard Enterprise, 337-TA-1429, 2024-12-19: +4.4%, by 10:43
- Sonos (as respondent), 337-TA-1329, 2025-04-08: -4.0%, by 13:34
- Super Micro Computer, 337-TA-1472, 2026-10-06: +3.7%, by 09:54
- T-Mobile, 337-TA-1480, 2026-09-15: -2.7%, by 12:05
- InterDigital, 337-TA-1481, 2026-08-13: -2.7%, by 10:39
- TE Connectivity, 337-TA-1446, 2026-04-29: +2.6%, by 11:40

**Reading these.** The ITC's big decisions come on published target dates, so they are not surprises. The unscheduled events are mostly settlements between a big company and a patent-licensing firm, and they move the stock by a few percent at most. The rare large unscheduled moves in this set are small companies (Shoals, T1 Energy, Beauty Health) whose case is a real share of the business. The biggest move in the set, Shoals in January 2025, came one day before a published target date, so traders already knew the decision was close.

## Fields and gaps

- `decision_time_et` is blank everywhere: no public source gives the minute.
- `revenue_at_stake_usd` and `revenue_at_stake_share` are blank: the companies do not break out revenue for the accused products in filings we could read automatically.
- `implied_move_before_decision` (the move options prices expected) is blank: no free source for expired option prices was used here.
- `settlement_amount_usd` is blank: ITC settlements are confidential.
- Revenue is the latest trailing-twelve-month (or annual, when that is all there is) XBRL revenue reported before filing. Market cap is shares outstanding from the SEC times the closing price on the filing date.
- CourtListener was not used; this case type is fully covered by ITC and Federal Register sources.

## How to rerun

```
python scripts/universe_itc337.py ids parse fr rows stats
```

Downloads are cached in `data/universe/itc337/raw/` (about 230 MB, not committed). Yahoo answered HTTP 429 (too many requests) to a full Chrome User-Agent for hours on 2026-10-14 but served a plain `Mozilla/5.0`, so the script sends that. The `rows` step stops asking Yahoo for the rest of a run once it sees a 429.
