<picture><source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.png"><img src="assets/banner-light.png" alt="Do prediction market prices mean what they say? A reliability diagram of 6,393 resolved Polymarket markets, priced a week before their scheduled end: the points sit close to the diagonal" width="100%"></picture>

A reproducible calibration study of 11,881 resolved Polymarket markets, the two analysis bugs that manufactured findings until I caught them, and a pre-registered test of the one finding that survived.

[![CI](https://github.com/Guinerve/calibration-atlas/actions/workflows/ci.yml/badge.svg)](https://github.com/Guinerve/calibration-atlas/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-2a78d6)
![Tests](https://img.shields.io/badge/tests-95%20passing-2a78d6)
![Holdout](https://img.shields.io/badge/holdout-blinded%2C%200%20of%2065%20events-52514e)
![Data](https://img.shields.io/badge/data-read%20only%20public%20API-52514e)

| [**Read the report**](reports/REPORT.md) | [**Open the explorer**](https://guinerve.github.io/calibration-atlas/) | [**Holdout test**](reports/HOLDOUT.md) | [**Reproduce it**](#reproduce) |
|---|---|---|---|
| Every table, interval and chart | Refit the slope live, by horizon and category | The macro finding, on new markets | `uv run calatlas report` |

## What it found, and in what

Everything below describes **one sample**: 11,881 markets from the 1,500 highest-volume closed Polymarket events, closing January 2024 to October 2026, collected on 12 October 2026. It was analysed after looking at the data, so these are findings about these markets, not about prediction markets in general.

| In this sample | Result | Status |
|---|---|---|
| **A week before the scheduled end, prices were well calibrated** | Recalibration slope b = **0.99 ± 0.03** (b = 1 is perfect), Brier score 0.056, across 6,393 markets in 785 events. | Exploratory |
| **Macro markets looked too timid** | Fitted alone, b = **1.66** (95% interval 1.21 to 2.10): macro favourites priced 50¢ to 95¢ won 26 of 30 times, where their prices implied about 21. Partial pooling shrinks it to **1.29** (0.91 to 1.81). | [Under a pre-registered test](#the-holdout-test) |
| **Political prices leaned slightly overconfident** | b = **0.89** (0.81 to 0.98), and 0.90 (0.82 to 0.99) after pooling. | Exploratory |
| **The one strategy tested made no reliable profit** | Refitting monthly and trading the gap a week before the scheduled end made **+0.8¢ per contract** after a 1¢ cost, 95% interval −1.3¢ to +3.0¢. 395 of its 1,117 trades fall in one month. | Exploratory |

The last row is about that strategy at that cost. It does not show that no strategy could profit: other signals, timings, sizing and execution were not tried.

"Macro" is a tag group: economy, Fed, inflation and jobs data, but also finance, business, stocks and earnings markets.

## The holdout test

The macro result was found after looking, in 65 events, and pooling halves its distance from 1. So it is being tested on data that did not exist when it was found: **markets that closed after the collection**, under rules frozen the day after in [PROTOCOL.md](PROTOCOL.md).

* **Same population.** The primary test uses events at least as big as the smallest event in the original sample ($5.77M traded). A secondary test drops that floor.
* **Read once.** On the first 65 such events to close (counted a week after closing, once settled), the original's size. Until then [`HOLDOUT.md`](reports/HOLDOUT.md) and the explorer show only a count, so the test can't be stopped early on a convenient result. If 65 haven't closed by 31 December 2027, it is read on what there is and labelled underpowered.
* **Verdict fixed in advance.** *Supported* if the one sided 95% lower bound on b is above 1; *reversed* if the 95% interval lies below 1; otherwise *not supported*. With 65 events the test has about 90% power if the true slope is 1.66 and 36% if it is 1.29, so *not supported* would mainly rule out an effect as large as first measured.
* **Tamper evident.** Every rule that picks markets, reads prices, fits the slope or reads the holdout is fingerprinted (SHA-256 of the code). CI fails if the fingerprint drifts from the one in `PROTOCOL.md`, so a rule can only change through a dated, logged amendment.

**Status at 12 October 2026 23:02 UTC: blinded, 0 of 65 events.** `uv run calatlas holdout` downloads markets closed since the cutoff and updates the count; in the original sample about five macro events this size closed each month in 2026, so expect the test to read in late 2027.

## Two bugs that made findings

Both bugs produced plausible, publishable results. Each one is now fixed, explained and pinned by a test.

### 1. Lookahead in the trade timing

The first backtest traded every market 7 days before it closed, and it **bought Yes in 100% of trades**. That was the clue.

"7 days before it closed" is not knowable at the time. 38% of markets close early: "Will X happen by June 30?" closes the moment X happens in May. Timing decisions from the actual close picks the moment using information from the future, and it quietly favours markets that are about to resolve Yes. The fitted intercept learned that, so the strategy bought Yes every time.

The fix is to decide at a time that was known in advance: **7 days before the scheduled end**, for markets still open then. The Yes share drops to 8.8%, and two category effects disappear:

| Category | b, timed from the actual close (leaky) | b, timed from the scheduled end |
|---|--:|--:|
| Sports | 1.20 (1.02 to 1.37) | 1.06 (0.86 to 1.26) |
| Crypto | 0.82 (0.66 to 0.97) | 0.97 (0.77 to 1.17) |
| Politics | 0.94 (0.83 to 1.04) | 0.89 (0.81 to 0.98) |
| Macro | 1.57 (1.16 to 1.97) | **1.66 (1.21 to 2.10)** |

Both timings stay in the code (`walk_forward(timing="close")`) so the comparison is reproducible:

<picture><source media="(prefers-color-scheme: dark)" srcset="reports/figures/backtest-dark.png"><img src="reports/figures/backtest-light.png" alt="Cumulative profit of the same strategy timed two ways: the leaky version appears to make about 39 dollars, the honest one about 9, inside its noise band" width="100%"></picture>

### 2. A clip that flattened the long shots

The recalibration takes logit(price), so prices are clipped away from 0 and 1. I first clipped at 1¢. But **46% of markets were priced under 1¢** at decision time, and Polymarket quotes down to 0.05¢. The clip squashed a 0.1¢ long shot and a 0.9¢ one into the same value, and since almost all of them resolved No, the fit read that as prices being too timid.

| Measure | Clipped at 1¢ | Clipped at 0.05¢ (no real price changed) |
|---|--:|--:|
| b, 7 days before scheduled end | 1.07 ± 0.03 | **0.99 ± 0.03** |
| b, 1 day before close, excluding early closes | 1.20 ± 0.04 | **1.09 ± 0.04** |
| b, macro | 1.71 ± 0.21 | **1.66 ± 0.23** |

The first draft of this README led with "favourites are underpriced the day before close". Most of that effect was the clip. The macro result survives both fixes, though partial pooling (below) takes some of the air out of it.

## Calibration by horizon

<picture><source media="(prefers-color-scheme: dark)" srcset="reports/figures/reliability-dark.png"><img src="reports/figures/reliability-light.png" alt="Reliability diagrams 30, 7 and 1 day before close; points sit close to the diagonal at every horizon" width="100%"></picture>

*How often Yes happened against the market price, 30, 7 and 1 day before close. Points on the dashed line are perfectly calibrated. Prices taken from the actual close peek at early resolutions, which is why the headline numbers use the scheduled end.*

## Categories, alone and pooled

<picture><source media="(prefers-color-scheme: dark)" srcset="reports/figures/category_slopes-dark.png"><img src="reports/figures/category_slopes-light.png" alt="Recalibration slope by category, alone and partially pooled: politics 0.89 and 0.90, sports 1.06 and 1.04, crypto 0.97 and 0.98, macro 1.66 and 1.29, culture 0.91 and 0.94" width="100%"></picture>

Each category's slope is first fitted alone. Five categories is a small family, and the one extreme value (macro, from just 65 events) is exactly what chance would produce now and then. A **Bayesian hierarchical model** asks how far the categories genuinely differ, and pulls each estimate toward the shared mean by as much as its own noise warrants:

* Politics, with 312 events and a tight estimate, barely moves (0.89 → 0.90) and stays below 1.
* Macro moves the most (1.66 → 1.29), and its credible interval now reaches 1.
* The prior on the spread between categories matters for macro: four times tighter gives 1.13, four times looser 1.33. The other categories move by 0.02 at most. The full table is in the report.

The model works from each category's event clustered estimate and standard error, so the correlation between markets in one event stays accounted for. Because the shared mean has a conjugate prior, the posterior is computed exactly on a grid instead of by MCMC: it runs in under a second and has no sampler to tune (`pooling.py`).

## Interactive explorer

**[guinerve.github.io/calibration-atlas](https://guinerve.github.io/calibration-atlas/)** recomputes everything live in the browser as you change the horizon, category, minimum volume and whether early closes count: the reliability diagram, Brier score and the recalibration slope with errors clustered by event. It also tracks the holdout count. A test checks that its JavaScript fit matches the Python analysis to six decimal places.

<a href="https://guinerve.github.io/calibration-atlas/"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/explorer-dark.png"><img src="assets/explorer-light.png" alt="The explorer: the question as a headline, the holdout count at 0 of 65 events, filters for horizon, category, volume and early closes, tiles for markets, Yes rate, Brier score and slope, and a reliability diagram" width="100%"></picture></a>

## Method

The full rules, frozen, are in [PROTOCOL.md](PROTOCOL.md). In short:

**Data.** Polymarket's public Gamma API (closed events with their markets and tags) and CLOB price history, collected on 12 October 2026: the 1,500 highest-volume closed events, with markets closing between January 2024 and October 2026. Every response is cached on disk with its download time.

**Selection.** Binary Yes/No markets that settled cleanly at 1 or 0, with at least $10,000 traded. Teams markets ("Lakers vs Celtics") and disputed or partial settlements are left out by rule, not by hand.

**Prices.** The last published price at or before each cutoff, never after it. The 30 and 7 day prices may be up to a day old (12 hourly data); the 1 day price must be within 3 hours (hourly data). A market without a fresh enough price is left out of that horizon, and the report states the coverage at each one.

**Scores.**
* Brier score, with the Murphy decomposition into reliability (miscalibration), resolution (how well prices separate outcomes) and uncertainty.
* A logistic recalibration, logit(P(Yes)) = a + b·logit(price). If b is above 1, prices are too timid at the extremes.

**Uncertainty.** Markets inside one event are strongly correlated (one winner among 30 candidates), so standard errors are clustered by event and bootstrap intervals resample whole events.

**Pooling.** b_hat ~ Normal(b, se), b ~ Normal(mu, tau), mu ~ Normal(1, 1), tau ~ HalfNormal(0.5), for categories with at least 100 markets in at least 10 events.

**Backtest.** Each month, refit the recalibration on markets that had **already resolved**, then trade markets whose decision time falls in that month. Buy whichever side the recalibrated probability favours by more than the cost. Settle on a $1 contract at a flat 1¢ cost per contract (half spread plus fees).

## How I know it's right

The tests check the properties that would make the results wrong if they broke:

* **Parameter recovery.** Markets simulated with a known bias (a, b) are fitted, and the true values come back within three standard errors (plus a 0.02 allowance). Prices below 1¢ keep their own logit.
* **Clustering works.** Duplicating markets inside an event does not shrink the standard errors or the bootstrap interval.
* **No future information.** Flipping every outcome after a cutoff leaves every earlier trading decision unchanged, including when markets settle weeks after their scheduled end (a test checks that this one fails if training keys on the scheduled end instead of the actual settlement). Prices are never read past their cutoff, and a market that had already closed at decision time is never traded.
* **The strategy can find an edge, and not invent one.** On simulated biased prices it profits; on calibrated prices it doesn't.
* **Pooling helps, and is computed exactly.** On simulated families of categories, pooled slopes land closer to the truth than slopes fitted alone, a precise category keeps its estimate, and a real difference survives. A test checks the closed form likelihood against scipy's multivariate normal density.
* **The rules are frozen.** The code's fingerprint must match `PROTOCOL.md`; changing a threshold, a tag list or a rule function changes it. The claim under test is recomputed from the committed data, so the protocol cannot misquote it.
* **The holdout can't be peeked at or moved.** While blinded, no output contains a slope. Once read, adding later events with a wildly different slope leaves the verdict unchanged. Markets already in the study, closed before the cutoff, or in events below the size floor never count toward the primary test. A simulated real effect is *supported*; a calibrated market is not.
* **The explorer agrees with the analysis.** The browser's slope, clustered errors, Brier score and bins are checked against the Python versions in CI, and a subset with no stable fit shows as such rather than as a runaway slope.
* **The Murphy terms add up** to the Brier score, and calibrated forecasts score near zero reliability.
* **Data collection.** HTTP tests run on a mock transport: paging, caching, retries on 429 and 5xx, permanent errors raised rather than hidden, and failed downloads recorded in an errors file rather than silently dropped. The live holdout listing is never served from the cache. The original collection had zero failures.

95 tests run on every push in GitHub Actions, with `ruff` for linting.

## Reproduce

```bash
git clone https://github.com/Guinerve/calibration-atlas && cd calibration-atlas
uv sync
uv run calatlas report    # rebuild REPORT.md, HOLDOUT.md, every chart and the explorer data (seconds, no network)
uv run pytest             # 95 tests, no network
```

That is the whole reproduction: `data/study.csv` (one row per market) and `data/holdout.csv` are committed, so nothing needs the API. Optional extras:

```bash
python3 -m http.server 5196 --bind 0.0.0.0 --directory docs   # view the explorer locally
uv run calatlas holdout                                       # fetch markets closed since the cutoff (minutes)
uv run calatlas collect --max-events 1500 --workers 6         # re-download the original sample (about 45 minutes)
uv run calatlas fingerprint                                   # print the protocol fingerprint of the current code
```

A fresh collection makes about 24,000 requests and caches them in `data/raw/`, so reruns are instant.

## Repository map

| Path | What it is |
|---|---|
| [`reports/REPORT.md`](reports/REPORT.md) | The full results, regenerated by `calatlas report` |
| [`reports/HOLDOUT.md`](reports/HOLDOUT.md) | The pre-registered macro test and its current status |
| [`PROTOCOL.md`](PROTOCOL.md) | The frozen sampling rules, holdout design and fingerprint |
| [`docs/`](docs) | The explorer, served by GitHub Pages (`stats.js` holds its statistics) |
| `data/study.csv`, `data/holdout.csv` | One row per market; `collection.json` and `holdout.json` record when |
| `src/calibration_atlas/fetch.py` | Polymarket API client with on-disk cache and retries |
| `src/calibration_atlas/dataset.py`, `markets.py` | Selection rules, horizon prices, the decision price |
| `src/calibration_atlas/collect.py` | Builds `study.csv` and `errors.csv` |
| `src/calibration_atlas/metrics.py` | Brier score, Murphy decomposition, reliability table, cluster bootstrap |
| `src/calibration_atlas/recalibration.py` | Logistic recalibration with clustered errors; market simulator |
| `src/calibration_atlas/pooling.py` | Bayesian hierarchical pooling of the category slopes |
| `src/calibration_atlas/backtest.py` | Walk forward refit and trading |
| `src/calibration_atlas/protocol.py`, `holdout.py` | The frozen protocol, its fingerprint, and the holdout test |
| `src/calibration_atlas/report.py`, `explorer.py` | Charts (light and dark), `REPORT.md`, and the explorer data |

## Limits

* **One sample.** The 1,500 highest-volume closed events, so liquid markets, not all of them. Lifetime volume is only known afterwards, so the selection looks back; the decision time avoids the worst of this but not all of it.
* **Exploratory.** Every result except the holdout was found after looking at the data. Only the macro slope is being tested on new markets; the rest has not been replicated.
* **One strategy, one cost.** Prices are Polymarket's published price history, not executable bid and ask quotes. The flat 1¢ cost is an assumption; real fills on thin markets would be worse, which only strengthens the result for this strategy. The backtest leans on one month: 395 of its 1,117 trades fall in June 2026.
* **Categories come from event tags**, which are imperfect, and "macro" is broad. Only 43% of markets have a price 30 days before close, because many are younger than that.
* **One venue.** Research on read only public data; no trades were placed, and nothing here is trading advice.

## Next

* Read the holdout once 65 primary events have closed.
* Add Kalshi as a second venue, leaving out its multi leg combination markets.
* Pool the intercept as well as the slope, and let the category effects vary with the horizon.

## Citing

If you use this, cite it with [`CITATION.cff`](CITATION.cff) (GitHub's "Cite this repository" button reads it). MIT licensed.
