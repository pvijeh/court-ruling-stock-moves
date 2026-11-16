# Drug-patent trial decisions, 2021 to today: the full list

**What this is**
- A list of every drug-patent case in three federal trial courts that reached a decision after a trial between 2021-01-01 and 2026-10-14, plus the cases that settled after the trial started or in the 90 days before a scheduled trial, plus every Federal Circuit (the appeals court for patent cases) decision on appeal from those cases. For each case it gives the listed companies involved and how their stock moved.
- The courts are the District of Delaware, the District of New Jersey and the Northern District of West Virginia. Almost all US generic-drug patent fights are tried in these three.
- The data is in `data/universe/drug_patent/cases.csv`. `scripts/universe_drug_patent.py` rebuilds it from public sources.

**Why it matters**
- The earlier study in this repo picked 40 dramatic rulings. A model trained on picked cases will overstate how much rulings move stocks. This list includes the quiet cases too.

**Terms**
- *Hatch-Waxman case*: a brand-drug company sues a generic maker after the generic files an ANDA (abbreviated new drug application, the FDA filing for a generic copy). The filing itself counts as infringement under 35 U.S.C. 271(e)(2), so the case is decided before the generic launches.
- *505(b)(2)*: an FDA filing for a changed version of an existing drug. These are fought the same way.
- *BPCIA case*: the same kind of fight over a biosimilar, a copy of a biologic drug.
- *Bench trial*: a trial decided by a judge, not a jury. The judge writes an opinion weeks or months later, on no set date.
- *Brand* / *challenger*: the patent owner / the generic or biosimilar maker.
- *Abnormal return*: the stock's move minus the move of XBI, a biotech index fund, over the same days. It strips out the market's move that day.

## How the list was built

**Where we looked**
- The Federal Judicial Center's Integrated Database (fjc.gov). It has one record per federal civil case, including nature-of-suit code 835 (ANDA patent cases), trial start and end dates, and how the case ended. It runs through 2026-06-30.
- GovInfo's US Courts collection (govinfo.gov): the written opinions and their docket text.
- The District of Delaware's opinions page (ded.uscourts.gov), 4,554 opinions from 2021 to 2026.
- The Federal Circuit's opinions list (cafc.uscourts.gov), for appeals.
- SEC EDGAR for share counts, revenue and the time of each company's 8-K or 6-K filing. Yahoo for daily prices.

**Steps**
- Took every patent case in the three courts whose last trial day was 2020-06-01 or later and that was an ANDA case or had drug companies on both sides: 103 dockets.
- Merged dockets tried together into one case, and dropped the cases that were not drug cases (for example 10X Genomics v. Bruker and United States v. Gilead).
- Read the conclusion of each post-trial opinion by hand to record the result and the decision date.
- As a check, scanned 1,095 opinions from 2021 on in patent cases (court pages and GovInfo) for words like "bench trial" and "findings of fact".
  - Delaware: all 41 post-trial drug opinions found this way were already on the list.
  - New Jersey and West Virginia: 424 opinions read, 39 looked like post-trial drug opinions. All but one were already on the list. The missing one was the 2024-12-17 decision in Janssen v. Mylan and Teva (Invega Sustenna), made after the Federal Circuit sent the case back; it is now a row. The other hits were fee motions, transfer and sealing orders, a default judgment and a product-injury case.
- Matched the listed brand and challenger in each case to its ticker, using the parent company where the party is a wholly owned unit (Sandoz to Novartis until its October 2023 spin-off, Hospira to Pfizer, Actavis to Teva, Mylan to Viatris).

## What we found

**Counts**
- 68 trial-court cases, 87 rows (one row per listed company per case, plus one row for each case with no US-listed party).
- By decision year (or end date, for settlements): 2021: 13, 2022: 15, 2023: 18, 2024: 13, 2025: 5, 2026: 4.
- By court: Delaware 47, New Jersey 17, Northern District of West Virginia 4.
- 51 cases had at least one US-listed company: 42 brand rows and 28 challenger rows.
- 23 Federal Circuit appeal decisions, 34 more rows (`case_type` = `drug_patent_appeal`).
- That is about 10 to 17 trial decisions a year, well below the 30 to 80 guessed at the start.

**Outcomes (from the brand's side)**
- Win 27, loss 18, split 8, settled after trial 8, settled shortly before trial 5, dismissed after trial 2.
- Novartis v. MSN (Entresto, D. Del. 22-1395, 2025-07-11) moved from settled to loss: its docket shows a trial opinion finding no infringement, which the court-database code had hidden.

**How long the wait is**
- From the last trial day to the decision: median 151 days; the middle half fall between 104 and 229 days.

**Stock moves on the decision (abnormal: the stock's return minus the biotech fund XBI's)**
- 65 listed-company rows have prices.
- One-day return where the posting minute is known (15 rows), otherwise the 2-day return (decision day plus the next), since the opinion may have come out after the close.
- Moved more than 5%: 17. More than 10%: 9. More than 25%: 5.
- Median move (up or down): 1.8%.
- Most moves are small because the drug is a small share of a large company (AbbVie, Johnson & Johnson, Merck) or because the result was expected.

**The 10 biggest moves**
- Pacira (PCRX), brand, Exparel patent held invalid, 2024-08-09: -48.2% (same day; the opinion was posted at 15:17).
- Heron Therapeutics (HRTX), brand, patent upheld against Fresenius Kabi, 2024-12-03: +35.0%.
- Vanda (VNDA), brand, Hetlioz patents lost to Teva, 2022-12-13: -34.8%.
- Teva (TEVA), challenger, lost the Invega Sustenna remand decision, 2024-12-17: +33.5%. Unrelated: Teva reported results for one of its own drugs in trials that day.
- Corcept (CORT), brand, Korlym case lost to Teva, 2023-12-29: -26.7% (next trading day; the opinion was posted at 16:36).
- Bausch Health (BHC), brand, Xifaxan split decision against Norwich, 2022-08-10: +19.7%.
- Liquidia (LQDA), challenger, split decision against United Therapeutics, 2022-08-31: -12.6%.
- Takeda (TAK), brand, Trintellix win, 2021-10-05: -10.5%. This is probably unrelated news, since the result was a win.
- Bausch Health (BHC), brand, Duobrii win against Padagis, 2022-12-01: +10.4%.
- Johnson & Johnson (JNJ), brand, Invega Sustenna win against Tolmar, 2024-02-26: -9.1%. Probably unrelated for a company this size.

**Appeals**
- Appeal decision: whether the Federal Circuit kept (affirmed), overturned (reversed) or sent back (vacated) the trial ruling. The script reads the court's one-line ruling, which sits just above the "COSTS" heading or at the end of the majority opinion, before any dissent (a judge's written disagreement). I read the conclusion of all 23 opinions by hand and every one matched. Each appeal row takes the confidence of the trial-court row it comes from, since the company match is the same.
- 30 rows with a listed company, from 19 appeals. Outcome from the brand's side: 11 wins, 8 losses, 11 split (part kept, part sent back or overturned). Allergan v. MSN (2024-08-13) is the one full reversal: the brand lost at trial and won on appeal.
- Moves are smaller than at trial: 28 rows have prices, 8 moved more than 5%, 2 more than 10%, none more than 25%. Median 3.8%.
- Biggest: Corcept -11.9% (2026-02-19, Korlym loss upheld) and Liquidia -11.1% (2023-07-24).

## Which outcomes can be traded on fast

**What we measured**
- *Posting time*: the minute the court put the opinion on its docket. CourtListener (a free mirror of court dockets) records it for many entries. The project's share of its free quota is about 15 requests a day, so the 45 listed cases with a known CourtListener docket were looked up in daily batches, newest first. All 45 are done (last batch 2026-10-15). The 46th, AstraZeneca v. Alembic (D. Del. 20-202), has no CourtListener docket ID I could confirm, so it has no posting time.
- The times are New York time. Check: Exelixis's opinion was posted at 11:00:04, and its stock jumped in the 11:00 minute.
- An opinion posted *under seal* (hidden from the public) does not count as public at its posting minute.
- Where the court time is missing and 1-minute prices exist (Polygon, last 2 years only), the script takes the first minute the stock jumped, marked "inferred from price".
- Bench opinions have no set date, so every trial decision except the Jazz v. Avadel jury verdict was a surprise in timing.

**What we found**
- Minute or hour time for 19 rows (15 cases), all decided from 2023 on. None of the 2021–22 docket entries on CourtListener carries a time: they came from uploaded documents rather than the live docket feed, so those rows stay at day precision.
- Came out during market hours (9:30 to 16:00) with no set date: 12 rows (10 cases). 9 rows (7 cases) are court decisions. 3 are settlements or dismissals, and none of those moved its stock more than 2.5%.
- The decisions, with the stock's move that day against XBI (the biotech index fund):
  - Exelixis (EXEL), Cabometyx win, 2024-10-15: opinion posted 11:00. The stock went from $26.37 to $27.89 within that minute and closed +8.4% against XBI. Exelixis's 8-K came at 16:15, 315 minutes later. Half the move was done in the first minute.
  - Pacira (PCRX), Exparel loss, 2024-08-09: opinion posted under seal at 15:17, yet the stock closed 48% lower that day, so the result was out before 16:00. Pacira's 8-K came at 19:23. Too old for 1-minute prices.
  - Regeneron (REGN) v. Mylan/Viatris (VTRS), Eylea biosimilar, 2023-12-27: the opinion was sealed at 12:50 and the clerk's judgment was public at 13:20. Regeneron +1.4%, Viatris -1.0%.
  - Sanofi (SNY) v. Actavis (Teva, TEVA), 2023-06-26: opinion posted 12:15, a win for Sanofi. Sanofi +2.6%, Teva +2.6%. Teva lost, so its rise was driven by other news.
  - Merck (MRK) v. Aurobindo et al., 2023-06-13: opinion posted 15:04, a win for Merck. Merck -1.7%.
  - Supernus (SUPN) v. Ajanta/Torrent, 2024-01-30: the opinion was sealed at 13:49; the order stating the result was public at 14:04. Supernus -0.2%.
  - Novartis (NVS) v. MSN, Entresto loss, 2025-07-11: opinion posted 10:01. Novartis -0.7%.
- Median absolute move of those 9 decision rows: 1.7%. Only Exelixis and Pacira moved more than 5%.
- Not counted: Janssen (J&J) v. Mylan/Teva, the 2024 Invega Sustenna decision on remand. The public opinion was posted 2024-12-17 at 15:28, but it was signed under seal on 2024-11-21, and J&J's 10-K says the decision was issued in November 2024. When the result first became public is not known.
- Median lead over the company's own release: 246 minutes, from 3 cases (Exelixis 315, Pacira 246, Heron 38).
- Median minutes to half the move: 0, from 2 cases (Exelixis, Heron). In both, the first minute after the news already made half the day's move, so speed is measured in seconds, not minutes.
- Correction: an earlier version gave Exelixis's release as an 08:00 8-K. That 8-K was about a Merck collaboration; the ruling 8-K was at 16:15. The script now only counts 8-Ks whose news section mentions the court.
- The company's own 8-K or 6-K time is known for 10 rows. SEC times are in UTC and were converted to New York time.

**Best examples to study** (big move, no set date)
- Market hours: Exelixis and Pacira, the two Liquidia-like cases so far.
- After the close: Heron (stock jumped at 16:37, 38 minutes before its 8-K) and Corcept (opinion at 16:36, -26.7% the next day).
- Time not known (the docket entry has a date only): Vanda, Bausch Health (twice) and Liquidia.

## What is missing

- **Settlements shortly before trial.** A "settlement shortly before trial" here means a case that settled or was dismissed in the 90 days before its trial was due to start. The free bulk court data has no scheduled trial dates, so I took every drug-patent case (code 835 in the FJC file, the federal courts' case database) that ended by settlement or dismissal after 2021, ran at least two years and had a listed party: 107 cases.
  - **Already on the list:** 11 of the 107 were trial cases already on the list (for example, Novartis v. MSN ended with a trial opinion). That leaves 96.
  - **SEC filings:** for 101 cases I searched the listed company's 10-K, 10-Q, 20-F and 6-K filings from the year before the case ended for a stated trial date. One case qualified: AstraZeneca v. Alembic (Tagrisso, D. Del. 20-202). Its trial was "scheduled for May 2022" and the case ended on 2022-04-25.
  - **Court dockets:** I searched the CourtListener copy of all 96 dockets (a docket is the court's running list of filings) for entries that set, move or record a trial date or a pretrial order. That took 10 requests, at 10 dockets each. I also fetched the newest 20 entries from the last 200 days for 15 of them. 41 dockets had at least one such entry.
  - **Four more qualify** and are now on the list as settled before trial:
    - Merck v. Apotex and Merck v. Zydus (D. Del. 19-313 and 19-314) ended 5 and 6 days before a trial set for 2021-10-04.
    - Otsuka v. Teva (D. Del. 22-513) ended 22 days before a trial set for 2024-10-15.
    - Novo Nordisk v. Mylan (D. Del. 22-1040) ended on 2024-10-02, 27 days before its final pretrial conference. The trial was most likely set for 2024-12-09. That date is inferred from two orders; no single entry states it.
  - **One already-tried case was missing:** Alkermes v. Teva over Vivitrol (D.N.J. 20-12470). It was tried in February 2023 and settled on 2023-08-30 before a decision, so it is now on the list as settled after trial.
  - **Likely, but not confirmed (not on the list):** in 4 cases the parties filed the joint proposed pretrial order (the trial plan, filed a few weeks before trial) within 60 days before the case ended, but no docket text gives the trial date. They are Otsuka v. Mylan (22-464), Intercept v. Apotex (20-1105), Pfizer v. Glenmark (19-1209) and Allergan/AbbVie v. MSN (23-794).
  - **Trials held in member cases:** the Entresto dockets 21-1760, 19-2021 and 20-74 show trials held in the Entresto MDL (MDL: many related cases handled together by one judge). They are not separate rows. Whether those trials are fully covered by the MDL's existing rows is not checked.
  - **The rest:** 55 dockets had no entry about a trial date on CourtListener, often because CourtListener holds only part of the docket. Several others had a trial date that had already passed or was more than 90 days away when the case ended. For example, Merck v. Mylan in West Virginia ended 98 days before trial. Not found does not mean ruled out.
  - **Total:** 5 cases settled shortly before trial (AstraZeneca plus these 4). The per-case results are in `data/universe/drug_patent/work/settle_docket.json`.
- **Posting times.** Docket entries were fetched for all 45 listed cases with a CourtListener docket. Only 15 cases, all from 2023 on, have a time; the 2021–22 entries carry a date only. AstraZeneca v. Alembic has no confirmed CourtListener docket.
- **Revenue at stake.** Filled for 23 of 38 brand rows. 18 come from the product sales tagged in the brand's 10-K or 20-F data on SEC (XBRL, the machine-readable version of the filing). For 5 more (Xifaxan, Entresto, Invega Trinza, Korlym, Trokendi XR) I read the figure by hand from the annual report's sales table, and the note says so. 13 are US-only figures; for the other 10 the filing gives no US split, so the worldwide figure is used and the note says so. J&J reports its Invega Sustenna and Invega Trinza injections as one combined sales line, so those rows carry the whole franchise. Of the 15 blank rows, 7 have no product-level sales figure in the filing, 5 have a brand that is not US-listed or no identified drug, and 3 (Sanofi's Jevtana, Takeda's Trintellix and Vyvanse) give product sales only in euros or yen, which I did not convert.
- **Some prices.** Endo (ENDP), BioDelivery Sciences (BDSI), Avadel (AVDL) and Amicus (FOLD) have no Yahoo history now. Market cap and revenue are blank for foreign companies that file under IFRS.
- **Federal Circuit appeals.** Only appeals whose opinion names the trial court's docket number are joined. Appeals of preliminary rulings (for example the Regeneron Eylea injunction appeals) are left out on purpose.
- **Cases after June 2026.** The FJC database stops at 2026-06-30. Trials that ended later are only partly covered, through the Delaware opinions page.
- **Confidence.** Rows marked "high" were checked against the opinion's conclusion. Rows marked "medium" or "low" rely on the FJC disposition code or a sealed opinion.

This is historical research, not investment advice.
