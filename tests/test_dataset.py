import math

from calibration_atlas.dataset import candidate_markets, decision_price, snapshot

HOUR, DAY = 3_600, 86_400
CLOSE = 1_735_689_600  # 2025-01-01T00:00:00Z


def market(**overrides):
    base = {
        "id": "m1", "question": "Will it happen?", "outcomes": '["Yes", "No"]',
        "outcomePrices": '["1", "0"]', "volumeNum": 50_000, "clobTokenIds": '["yes-token", "no-token"]',
        "closedTime": "2025-01-01 00:00:00+00", "endDate": "2025-01-01T00:00:00Z", "negRisk": False,
    }
    return base | overrides


EVENT = {
    "id": "e1",
    "tags": [{"label": "Politics"}, {"label": "Elections"}],
    "markets": [
        market(),
        market(id="small", volumeNum=2_000),
        market(id="teams", outcomes='["Lakers", "Celtics"]'),
        market(id="unsettled", outcomePrices='["0.5", "0.5"]'),
        market(id="early", closedTime="2024-12-01 00:00:00+00"),
    ],
}


def test_only_cleanly_settled_yes_no_markets_with_enough_volume_are_kept():
    assert [m["market_id"] for m in candidate_markets(EVENT)] == ["m1", "early"]


def test_candidate_carries_event_category_token_and_outcome():
    m = candidate_markets(EVENT)[0]
    assert (m["event_id"], m["category"], m["yes_token"], m["outcome"]) == ("e1", "politics", "yes-token", 1)
    assert m["closed_ts"] == CLOSE


def test_market_closing_a_month_before_its_end_date_is_flagged_early():
    flags = {m["market_id"]: m["resolved_early"] for m in candidate_markets(EVENT)}
    assert flags == {"m1": False, "early": True}


def test_snapshot_reads_each_horizon_before_the_close():
    history = [
        {"t": CLOSE - 40 * DAY, "p": 0.30},
        {"t": CLOSE - 30 * DAY - HOUR, "p": 0.35},
        {"t": CLOSE - 7 * DAY - HOUR, "p": 0.50},
        {"t": CLOSE - DAY - HOUR, "p": 0.80},
        {"t": CLOSE - HOUR, "p": 0.99},
    ]
    s = snapshot(CLOSE, history)
    assert (s["price_30d"], s["price_7d"], s["price_1d"]) == (0.35, 0.50, 0.80)


def test_snapshot_is_missing_when_the_market_is_younger_than_the_horizon():
    s = snapshot(CLOSE, [{"t": CLOSE - 3 * DAY, "p": 0.6}, {"t": CLOSE - DAY - HOUR, "p": 0.7}])
    assert math.isnan(s["price_30d"]) and math.isnan(s["price_7d"])
    assert s["price_1d"] == 0.7


def test_one_day_snapshot_needs_an_hourly_point():
    # 12-hourly data alone can be up to 12 hours stale at the one-day mark: too stale.
    s = snapshot(CLOSE, [{"t": CLOSE - DAY - 10 * HOUR, "p": 0.7}])
    assert math.isnan(s["price_1d"])


def test_decision_price_is_read_seven_days_before_the_scheduled_end():
    end = CLOSE + 3 * DAY  # closed early, but after the decision time
    history = [{"t": end - 8 * DAY, "p": 0.40}, {"t": end - 7 * DAY - HOUR, "p": 0.45},
               {"t": CLOSE - DAY, "p": 0.97}]
    assert decision_price(closed_ts=CLOSE, end_ts=end, history=history) == 0.45


def test_no_decision_price_for_a_market_already_closed_at_decision_time():
    # Closed 20 days before its scheduled end: at end - 7 days it no longer traded.
    history = [{"t": CLOSE - 30 * DAY, "p": 0.40}, {"t": CLOSE - DAY, "p": 0.97}]
    assert math.isnan(decision_price(closed_ts=CLOSE, end_ts=CLOSE + 20 * DAY, history=history))
