"""Build the study table: one row per resolved market, with its price at each horizon.

The selection rules are fixed here, before any results are looked at:
binary Yes/No markets that settled cleanly at 1 or 0, with at least MIN_VOLUME traded.
"""

from __future__ import annotations

import json
import math

from .markets import (
    category_from_tags,
    outcome_from_prices,
    parse_time,
    price_at,
    resolved_early,
)

MIN_VOLUME = 10_000  # US dollars traded over the market's life

HOUR, DAY = 3_600, 86_400

# Horizon name -> (seconds before the close, how stale the price may be).
# 30- and 7-day prices come from 12-hourly data; the 1-day price needs hourly data.
HORIZONS = {
    "30d": (30 * DAY, DAY),
    "7d": (7 * DAY, DAY),
    "1d": (DAY, 3 * HOUR),
}

# The backtest decides 7 days before the *scheduled* end, a time known in advance.
# "7 days before the close" is not: an early close is only known once it happens.
DECISION_BEFORE_END = 7 * DAY


def candidate_markets(event: dict) -> list[dict]:
    """The event's markets that meet the selection rules, with the fields the study uses."""
    tags = [t.get("label", "") for t in event.get("tags") or []]
    category = category_from_tags(tags)
    kept = []
    for m in event.get("markets") or []:
        outcome = outcome_from_prices(m.get("outcomePrices"), m.get("outcomes"))
        closed, end = parse_time(m.get("closedTime")), parse_time(m.get("endDate"))
        volume = float(m.get("volumeNum") or 0)
        if outcome is None or closed is None or end is None or volume < MIN_VOLUME:
            continue
        try:
            yes_token = json.loads(m["clobTokenIds"])[0]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        kept.append({
            "market_id": str(m["id"]),
            "event_id": str(event["id"]),
            "question": m.get("question", ""),
            "category": category,
            "tags": "|".join(tags),
            "yes_token": yes_token,
            "outcome": outcome,
            "volume": volume,
            "closed_ts": int(closed.timestamp()),
            "end_ts": int(end.timestamp()),
            "resolved_early": resolved_early(closed, end),
            "neg_risk": bool(m.get("negRisk")),
        })
    return kept


def snapshot(closed_ts: int, history: list[dict]) -> dict[str, float]:
    """The price at each horizon before the close; NaN where there is no fresh price."""
    out = {}
    for name, (before, staleness) in HORIZONS.items():
        p = price_at(history, cutoff=closed_ts - before, max_staleness=staleness)
        out[f"price_{name}"] = math.nan if p is None else p
    return out


def decision_price(closed_ts: int, end_ts: int, history: list[dict]) -> float:
    """The price 7 days before the scheduled end; NaN if the market had already closed then
    or has no fresh price."""
    decision_ts = end_ts - DECISION_BEFORE_END
    if closed_ts <= decision_ts:
        return math.nan
    p = price_at(history, cutoff=decision_ts, max_staleness=HORIZONS["7d"][1])
    return math.nan if p is None else p
