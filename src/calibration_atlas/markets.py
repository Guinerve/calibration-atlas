"""Turn raw Polymarket market data into the facts the study needs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

# Checked in this order: a market tagged both "Politics" and "Sports" is about sports.
CATEGORY_TAGS: list[tuple[str, set[str]]] = [
    ("sports", {"sports", "nba", "nfl", "mlb", "nhl", "soccer", "football", "tennis", "golf",
                "ufc", "mma", "boxing", "f1", "formula 1", "cricket", "esports", "ncaa",
                "basketball", "baseball", "hockey", "olympics", "fifa world cup"}),
    ("crypto", {"crypto", "bitcoin", "ethereum", "solana", "crypto prices", "xrp", "dogecoin"}),
    ("macro", {"economy", "fed", "fed rates", "fomc", "inflation", "economic policy", "finance",
               "business", "stocks", "earnings", "interest rates", "gdp", "jobs report",
               "recession", "tariffs"}),
    ("weather", {"weather", "climate", "climate & science", "hurricanes", "temperature"}),
    ("politics", {"politics", "elections", "us election", "global elections", "world elections",
                  "geopolitics", "world", "trump", "middle east", "ukraine", "congress",
                  "courts", "us politics"}),
    ("culture", {"culture", "pop culture", "movies", "music", "awards", "oscars", "tech", "ai",
                 "science", "mentions", "celebrities", "tv"}),
]


def category_from_tags(tags: list[str]) -> str:
    labels = {t.strip().lower() for t in tags}
    for category, members in CATEGORY_TAGS:
        if labels & members:
            return category
    return "other"


def outcome_from_prices(outcome_prices: str | None, outcomes: str | None) -> int | None:
    """1 if Yes won, 0 if No won, None unless a Yes/No market settled cleanly at 1 or 0."""
    try:
        names = [n.strip().lower() for n in json.loads(outcomes or "")]
        prices = [float(p) for p in json.loads(outcome_prices or "")]
    except (ValueError, TypeError):
        return None
    if names != ["yes", "no"] or sorted(prices) != [0.0, 1.0]:
        return None
    return int(prices[0] == 1.0)


def parse_time(value: str | None) -> datetime | None:
    """Polymarket uses both '2024-11-06 15:17:41+00' and '2024-11-06T15:17:41Z'."""
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if text.endswith("+00"):
        text += ":00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def price_at(history: list[dict], cutoff: float, max_staleness: float) -> float | None:
    """The last price at or before ``cutoff`` (unix seconds), or None if there is none
    or it is more than ``max_staleness`` seconds old. Never looks past the cutoff."""
    best = None
    for point in history:
        t = point["t"]
        if t <= cutoff and (best is None or t > best["t"]):
            best = point
    if best is None or cutoff - best["t"] > max_staleness:
        return None
    return float(best["p"])


EARLY_MARGIN = timedelta(days=1)


def resolved_early(closed: datetime, end: datetime) -> bool:
    """True if trading closed more than a day before the scheduled end, which usually
    means the event already happened ("Will X happen by June 30?" resolving Yes in May).
    Prices shortly before such a close already know the answer."""
    return closed < end - EARLY_MARGIN
