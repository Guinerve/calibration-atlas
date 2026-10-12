from datetime import UTC, datetime, timedelta

import pytest

from calibration_atlas.markets import (
    category_from_tags,
    outcome_from_prices,
    parse_time,
    price_at,
    resolved_early,
)

DAY = 86_400


def test_outcome_is_1_when_yes_settled_at_one():
    assert outcome_from_prices('["1", "0"]', '["Yes", "No"]') == 1


def test_outcome_is_0_when_no_settled_at_one():
    assert outcome_from_prices('["0", "1"]', '["Yes", "No"]') == 0


@pytest.mark.parametrize("prices", ['["0.5", "0.5"]', '["0.97", "0.03"]', "", None])
def test_outcome_is_none_unless_cleanly_settled(prices):
    assert outcome_from_prices(prices, '["Yes", "No"]') is None


def test_outcome_is_none_for_markets_that_are_not_yes_no():
    assert outcome_from_prices('["1", "0"]', '["Lakers", "Celtics"]') is None


def test_category_comes_from_the_first_matching_tag_group():
    assert category_from_tags(["All", "Trump", "Politics", "US Election"]) == "politics"
    assert category_from_tags(["Sports", "Soccer", "FIFA World Cup"]) == "sports"
    assert category_from_tags(["Fed Rates", "Economy", "Jerome Powell"]) == "macro"
    assert category_from_tags(["Crypto", "Bitcoin"]) == "crypto"
    assert category_from_tags(["Hide From New", "Culture"]) == "culture"
    assert category_from_tags(["Recurring"]) == "other"


def test_sports_beats_politics_when_both_tags_are_present():
    # e.g. "Will the President attend the Super Bowl?" is filed under both
    assert category_from_tags(["Politics", "Sports", "NFL"]) == "sports"


HISTORY = [{"t": 1_000 * DAY, "p": 0.40}, {"t": 1_005 * DAY, "p": 0.55}, {"t": 1_010 * DAY, "p": 0.70}]


def test_price_at_uses_the_last_point_at_or_before_the_cutoff():
    assert price_at(HISTORY, cutoff=1_007 * DAY, max_staleness=3 * DAY) == 0.55
    assert price_at(HISTORY, cutoff=1_005 * DAY, max_staleness=3 * DAY) == 0.55


def test_price_at_never_uses_a_point_after_the_cutoff():
    assert price_at(HISTORY, cutoff=1_004 * DAY, max_staleness=10 * DAY) == 0.40
    assert price_at(HISTORY, cutoff=999 * DAY, max_staleness=10 * DAY) is None


def test_price_at_rejects_a_stale_point():
    assert price_at(HISTORY, cutoff=1_009 * DAY, max_staleness=3 * DAY) is None


def test_price_at_handles_unsorted_history():
    shuffled = [HISTORY[2], HISTORY[0], HISTORY[1]]
    assert price_at(shuffled, cutoff=1_007 * DAY, max_staleness=3 * DAY) == 0.55


def test_parse_time_reads_both_polymarket_formats():
    expected = datetime(2024, 11, 6, 15, 17, 41, tzinfo=UTC)
    assert parse_time("2024-11-06 15:17:41+00") == expected
    assert parse_time("2024-11-06T15:17:41Z") == expected
    assert parse_time(None) is None


def test_market_that_closed_well_before_its_end_date_resolved_early():
    end = datetime(2025, 6, 30, tzinfo=UTC)
    assert resolved_early(closed=end - timedelta(days=10), end=end)
    assert not resolved_early(closed=end + timedelta(hours=5), end=end)
    assert not resolved_early(closed=end - timedelta(hours=12), end=end)
