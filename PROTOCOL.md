# Study protocol

Frozen on **13 October 2026**, the day after the original collection and before any market that closed after it was looked at. This file states the rules; [`src/calibration_atlas/protocol.py`](src/calibration_atlas/protocol.py) fingerprints the code that implements them, and CI fails if that code changes without an amendment below.

## Status of the existing results

Everything in [`reports/REPORT.md`](reports/REPORT.md) comes from one sample, collected on 12 October 2026, and was analysed after looking at it. Two analysis bugs were found and fixed along the way (see the README). Those results are **exploratory**: they describe that sample under that analysis. The one result singled out for confirmation is the macro slope, tested below on new data.

## Sampling rules

A market enters the study if all of these hold. The rules apply market by market, inside events listed by Polymarket's public Gamma API.

1. **Binary.** Its outcomes are exactly `["Yes", "No"]`.
2. **Settled cleanly.** Its final outcome prices are exactly 1 and 0. Disputed, partial or 50/50 settlements are left out.
3. **Traded.** At least **$10,000** traded over its life (`volumeNum`).
4. **Dated.** It has an actual close time and a scheduled end date.
5. **Priced.** It has a Yes token whose price history can be downloaded.

**Category** comes from the event's tags, checked in a fixed order (sports, crypto, macro, weather, politics, culture; anything else is "other"). The tag lists are in `markets.py`. "Macro" means tagged economy, Fed, FOMC, inflation, economic policy, finance, business, stocks, earnings, interest rates, GDP, jobs report, recession or tariffs: it covers finance and company markets, not only macroeconomics.

**Early resolution.** A market closed more than one day before its scheduled end resolved early.

## Price rules

* A price is the last published price **at or before** the moment it is read, never after.
* History comes from the CLOB price history: the whole life at 12 hour resolution, plus hourly points for the 14 days before the close.
* 30 and 7 days before close: the price may be up to 1 day old. 1 day before close: up to 3 hours old. A market without a fresh enough price is left out of that horizon.
* **Decision time**: 7 days before the **scheduled** end, for markets still open then (price up to 1 day old). This is the time used for categories, the backtest and the holdout, because it is known in advance.

## Analysis rules

* Recalibration: logit(P(Yes)) = a + b·logit(price), fitted by maximum likelihood, with prices clipped to [0.0005, 0.9995] and standard errors clustered by event.
* A category gets its own slope with at least 100 markets in at least 10 events.

## Pre-registered holdout test

**Hypothesis.** In macro markets, priced at the decision time, the recalibration slope b is above 1: prices are too timid at the extremes.

**Where it came from.** In the original sample: b = 1.66 (95% interval 1.21 to 2.10), 471 markets in 65 events, found after looking at the data. Partial pooling across categories shrank it to 1.29 (0.91 to 1.81).

**New data.** Markets that closed after **12 October 2026 06:22:23 UTC**, the moment the last event page of the original collection was downloaded. Both the market and its event must have closed after that moment, and no market may appear in `data/study.csv`.

**Populations.**
* *Primary*: events with at least **$5,769,105** traded, the lifetime volume of the 1,500th (smallest) event in the original sample. This keeps the population the original claim was made about.
* *Secondary*: every event, with each market still needing $10,000 traded. This asks whether the pattern holds in smaller events too. It is read with the primary and does not decide the verdict.

**When it is read.** Once, on the first **65** primary events to close (the original's size), in order of the event's close time. An event counts only once it closed at least **7 days** before the holdout was downloaded, so its markets have settled and the first 65 cannot change on a later run. Events that close after the deadline never count. Later events never enter, so the verdict cannot drift. Until then only counts are published, never a slope. If 65 primary events have not closed by **31 December 2027**, the test is read on the events there are and labelled underpowered. The secondary population is read on its events that closed no later than the last primary event in the confirmatory sample.

**Verdict.** With errors clustered by event:
* *supported* if the one sided 95% lower bound on b is above 1;
* *reversed* if the two sided 95% interval lies entirely below 1;
* *not supported* otherwise.

**Power.** If the standard error shrinks with the square root of the number of events, 65 events give a *supported* verdict with probability about 90% if the true slope is 1.66, and about 36% if the true slope is 1.29. *Not supported* would mostly rule out an effect as large as first measured; it would be weak evidence that macro prices are calibrated.

**How to run it.** `uv run calatlas holdout` downloads every event closed since the cutoff and regenerates [`reports/HOLDOUT.md`](reports/HOLDOUT.md). `uv run calatlas report` regenerates it offline from `data/holdout.csv`.

## Amendments

None. An amendment states its date, what changed and why, whether any holdout data had been seen, and the new fingerprint.

## Fingerprint

`uv run calatlas fingerprint` prints the SHA-256 of the rules and holdout design as the code stands. The frozen value:

Fingerprint: `24439a89f86296b545d0940243e5f50d628190110854643b5dc54491e67c2e2a`
