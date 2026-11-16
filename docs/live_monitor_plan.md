# Live ruling monitor: plan

**Executive summary**
- **What this is:** a plan for a system that watches pending cases during market hours, notices a ruling on the court's or the patent office's own site, works out which stock it affects and whether it is good or bad for the company, and acts within 30 seconds.
- **Why it matters:** in the case lists, the big unscheduled rulings came out hours before the company's own release. For drug patents, though, half the day's move happened in the first minute, so a slow alert gets nothing.
- **Where we looked:** the free public feeds of the courts and the patent office, checked from this machine on 2026-10-19, plus the PTAB case list in `data/universe/ptab/cases.csv`.
- **What we found so far:**
  - The District of Delaware, where most drug-patent trials are held, publishes a free RSS feed of all new docket entries with no login: https://ecf.ded.uscourts.gov/cgi-bin/rss_outside.pl. Each item names the case and the entry type. The Northern District of West Virginia has the same feed. New Jersey's address was refused from this machine.
  - PTAB final decisions are close to scheduled. The law sets a one-year deadline from the start of the trial, and 66% of the 2,307 decided trials in our list were decided 355 to 366 days after they started. So on any day only a few trials need watching.
  - Matching the ruling to the company needs no guesswork: the watchlist is built in advance from cases where we already know the stock.
- **Warning about the court RSS feeds:** after the close on 2026-10-19, polled every 2 minutes, the feeds' "last rebuilt" time (`lastBuildDate`) changed only about once an hour: Delaware at 20:07 and 21:07 UTC, West Virginia at 20:16 and 21:16. The server sends `Cache-Control: max-age=0`, so a cache isn't holding the feed back; the court seems to rebuild it on a schedule. The 22:07:22 UTC Delaware rebuild added 12 docket entries filed since the previous rebuild, and they reached the feed a median of 55 minutes after their docket time (between 10 and 60 minutes). If that also holds during market hours, the RSS feeds are too slow for 30 seconds, and the fast route is each watched case's PACER docket.
- **Still open:** how often the feeds refresh during market hours, and whether the trade pays (see `docs/intraday_backtest.md`).

## How it would work

1. **Watchlist (built each morning).**
   - Drug patents: tried cases still waiting for the judge's opinion, with their stock.
   - PTAB: trials whose one-year deadline is within the next 10 days, with each company's role (petitioner or patent owner).
   - Merger challenges: suits where a ruling on the government's injunction request is pending.
2. **Polling (inside each source's limits).**
   - Court RSS feeds: one request returns every new entry in that court, so polling covers every watched case at once. Even every 15 seconds is only 4 requests a minute per court. Before going live, check each court's terms and keep the rate at a level the court would accept.
   - P-TACTS (PTAB): one request per trial; earlier work was blocked after bursts but ran for hours at one request every 2.5 seconds. With about 5 trials due on a given day, each one is checked about every 12 seconds.
3. **Match.** Each feed item carries the case number, and the case number is the watchlist key.
4. **Read the outcome.**
   - PTAB: the decision's title states the result ("All Challenged Claims Unpatentable"). Turn it into good or bad for the company using its role.
   - Court opinions: download the opinion and have a fast model read the conclusion and order section. Expected to take a few seconds, not yet measured.
   - Sealed opinions ("SEALED MEMORANDUM OPINION"): the outcome can't be read. Alert only. Pacira's opinion was sealed, and the stock still fell 48% that day.
5. **Act.** Phase 1 alerts only and logs the seconds each step took. Phase 2 paper trades: orders go to a broker's fake-money account. Live trading only on Peter's own account, after he explicitly says go.

## Measurements before going live
- **Feed refresh time:** how many seconds pass between the court's docket time on an entry and its appearance in the RSS feed, during market hours.
- **Total time:** seconds from the feed showing an entry to an order being ready.
- **Accuracy:** how often the outcome reader gets good or bad right, tested on the rulings we already have.
