"""The frozen study protocol: sampling rules, and the pre-registered holdout test.

Everything that decides which markets enter the study, which price is read for each, how
the slope is fitted, and how the holdout is read is fingerprinted here. The fingerprint is recorded in PROTOCOL.md,
and a test fails if any of it changes, so a rule cannot be adjusted after seeing holdout
data without a dated amendment in PROTOCOL.md.

The holdout tests one hypothesis, found in the original sample after looking at the data:
in finance and macro markets, priced 7 days before their scheduled end, the recalibration
slope b is above 1 (prices too timid at the extremes).
"""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, datetime

from . import dataset, fetch, markets, recalibration

FROZEN_ON = "2026-10-13"

# The last event page of the original collection was downloaded at this moment. Every
# market that closed after it is new data: none of it could have shaped the rules.
CUTOFF = datetime(2026, 10, 12, 6, 22, 23, tzinfo=UTC)
CUTOFF_TS = int(CUTOFF.timestamp())

# The original sample was the 1,500 highest-volume closed events; the 1,500th had this
# lifetime volume. The primary holdout keeps the same population: events at least this big.
PRIMARY_MIN_EVENT_VOLUME = 5_769_105
# The secondary holdout drops the event floor (markets still need MIN_VOLUME each).
SECONDARY_MIN_EVENT_VOLUME = dataset.MIN_VOLUME

HYPOTHESIS = {
    "category": "macro",
    "price": "price_sched_7d",  # 7 days before the scheduled end, markets still open then
    "claim": "b > 1",
}
ORIGINAL = {"b": 1.66, "low": 1.21, "high": 2.10, "pooled": 1.29, "events": 65, "markets": 471}

# The test is read once, on the first MIN_EVENTS qualifying events in order of closing, the
# size of the original macro sample. Until then only counts are shown. If the count is not
# reached by DEADLINE, the test is read on what there is and labelled underpowered.
MIN_EVENTS = 65
# An event counts once it closed at least this long before the holdout was collected, so its
# markets have settled and the first MIN_EVENTS cannot change on a later run.
SETTLE_DAYS = 7
DEADLINE = datetime(2027, 12, 31, tzinfo=UTC)
ALPHA = 0.05  # one sided: supported if the lower 95% one sided bound on b is above 1


def _rules() -> list:
    """Every rule that decides which markets enter, which price is read, and how b is fitted.
    Read at call time, so the fingerprint always reflects the code as it runs."""
    # holdout imports this module, so it is imported here, once both are loaded
    from . import holdout, report

    return [
        dataset.MIN_VOLUME, dataset.HORIZONS, dataset.DECISION_BEFORE_END,
        dataset.candidate_markets, dataset.snapshot, dataset.decision_price,
        markets.CATEGORY_TAGS, markets.category_from_tags, markets.outcome_from_prices,
        markets.parse_time, markets.price_at, markets.EARLY_MARGIN, markets.resolved_early,
        recalibration.CLIP, recalibration.logit, recalibration.fit_recalibration,
        fetch.FULL_FIDELITY_MINUTES, fetch.RECENT_FIDELITY_MINUTES, fetch.RECENT_WINDOW_SECONDS,
        fetch.Fetcher.history, fetch.Fetcher.closed_since,
        holdout.holdout_markets, holdout._population, holdout._event_order, holdout._fit,
        holdout.verdict, holdout.evaluate, report.CATEGORY_RULES,
    ]


def _design() -> list:
    return [FROZEN_ON, CUTOFF_TS, PRIMARY_MIN_EVENT_VOLUME, SECONDARY_MIN_EVENT_VOLUME,
            HYPOTHESIS, ORIGINAL, MIN_EVENTS, SETTLE_DAYS, DEADLINE.isoformat(), ALPHA]


def _canonical(item) -> str:
    if callable(item):
        return inspect.getsource(item).replace("\r\n", "\n")
    if isinstance(item, (list, tuple)):  # CATEGORY_TAGS holds sets: sort them
        return json.dumps([_canonical(x) for x in item])
    if isinstance(item, set):
        return json.dumps(sorted(item))
    return json.dumps(item, sort_keys=True, default=str)


def fingerprint() -> str:
    """SHA-256 over the sampling rules and the holdout design, as they are now."""
    text = "\n".join(_canonical(x) for x in [*_rules(), *_design()])
    return hashlib.sha256(text.encode()).hexdigest()
