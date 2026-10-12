import numpy as np
import pandas as pd
import pytest

from calibration_atlas.backtest import trade_pnl, walk_forward
from calibration_atlas.recalibration import simulate_markets

DAY = 86_400
START = 1_672_531_200  # 2023-01-01T00:00:00Z


def timed_markets(a, b, n, seed, months=24):
    """Simulated markets spread evenly over ``months``, each priced 7 days before its scheduled
    end (which is also when it closes)."""
    sim = simulate_markets(a=a, b=b, n=n, seed=seed, markets_per_event=2)
    rng = np.random.default_rng(seed)
    closed = START + rng.uniform(0, months * 30 * DAY, n).astype(int)
    return pd.DataFrame({
        "market_id": [f"m{i}" for i in range(n)],
        "event_id": sim["event"].astype(str),
        "outcome": sim["outcome"],
        "price_sched_7d": sim["price"],
        "closed_ts": closed,
        "end_ts": closed,
    })


def test_yes_and_no_trades_are_settled_correctly():
    assert trade_pnl("yes", price=0.30, outcome=1, cost=0.01) == pytest.approx(1 - 0.31)
    assert trade_pnl("yes", price=0.30, outcome=0, cost=0.01) == pytest.approx(-0.31)
    assert trade_pnl("no", price=0.30, outcome=0, cost=0.01) == pytest.approx(1 - 0.71)
    assert trade_pnl("no", price=0.30, outcome=1, cost=0.01) == pytest.approx(-0.71)


def test_decisions_never_depend_on_outcomes_that_were_not_known_yet():
    df = timed_markets(a=0.0, b=1.4, n=6_000, seed=1)
    cutoff = START + 15 * 30 * DAY
    flipped = df.copy()
    later = flipped["closed_ts"] >= cutoff
    flipped.loc[later, "outcome"] = 1 - flipped.loc[later, "outcome"]

    def decisions_before_cutoff(frame):
        trades = walk_forward(frame, cost=0.01, min_train=500)
        early = trades[trades["month_start"] <= cutoff]
        return early.set_index("market_id")["side"].sort_index()

    original = decisions_before_cutoff(df)
    assert len(original) > 100
    pd.testing.assert_series_equal(original, decisions_before_cutoff(flipped))


def test_no_trades_until_enough_resolved_markets_to_learn_from():
    df = timed_markets(a=0.0, b=1.4, n=3_000, seed=2)
    trades = walk_forward(df, cost=0.01, min_train=1_000)
    first_month = trades["month_start"].min()
    known_by_then = (df["closed_ts"] < first_month).sum()
    assert known_by_then >= 1_000


def test_strategy_profits_when_prices_are_biased():
    trades = walk_forward(timed_markets(a=0.0, b=1.6, n=20_000, seed=3),
                          cost=0.01, min_train=500)
    assert trades["pnl"].mean() > 0.01


def test_strategy_does_not_profit_when_prices_are_already_calibrated():
    trades = walk_forward(timed_markets(a=0.0, b=1.0, n=20_000, seed=4),
                          cost=0.01, min_train=500)
    assert trades["pnl"].mean() < 0.005


def test_markets_without_a_price_at_the_horizon_are_skipped():
    df = timed_markets(a=0.0, b=1.4, n=3_000, seed=5)
    df.loc[df.index[-500:], "price_sched_7d"] = np.nan
    trades = walk_forward(df, cost=0.01, min_train=500)
    assert not set(trades["market_id"]) & set(df["market_id"].iloc[-500:])


def test_trades_are_timed_from_the_scheduled_end_not_the_unknowable_close():
    df = timed_markets(a=0.0, b=1.4, n=6_000, seed=6)
    # The last market closes early, three months before its scheduled end.
    df.loc[df.index[-1], "end_ts"] = df["closed_ts"].iloc[-1] + 90 * DAY
    df.loc[df.index[-1], "closed_ts"] = df["end_ts"].iloc[-1] - 3 * DAY
    df.loc[df.index[-1], "price_sched_7d"] = 0.05  # far from fair, so it is traded
    trades = walk_forward(df, cost=0.01, min_train=500).set_index("market_id")
    decision = pd.Timestamp(df["end_ts"].iloc[-1] - 7 * DAY, unit="s").to_period("M").start_time
    assert pd.Timestamp(trades.loc[df["market_id"].iloc[-1], "month_start"], unit="s") == decision


def test_close_timing_reproduces_the_leaky_version_for_comparison():
    df = timed_markets(a=0.0, b=1.4, n=6_000, seed=7)
    df["price_7d"] = df["price_sched_7d"]
    df["end_ts"] = df["closed_ts"] + 60 * DAY  # every market closes early
    leaky = walk_forward(df, cost=0.01, min_train=500, timing="close")
    months = pd.to_datetime(leaky["month_start"], unit="s")
    closes = pd.to_datetime(df.set_index("market_id").loc[leaky["market_id"], "closed_ts"]
                            - 7 * DAY, unit="s").dt.to_period("M").dt.start_time
    assert len(leaky) > 100 and (months.to_numpy() == closes.to_numpy()).all()


def test_training_waits_for_late_resolutions_even_when_the_scheduled_end_has_passed():
    # Markets often settle after their scheduled end; until then the outcome is unknown.
    df = timed_markets(a=0.0, b=1.4, n=6_000, seed=8)
    df["end_ts"] = df["closed_ts"] - 60 * DAY
    df["price_sched_7d"] = df["price_sched_7d"].where(df["closed_ts"] > df["end_ts"] - 7 * DAY)
    cutoff = START + 15 * 30 * DAY
    flipped = df.copy()
    later = flipped["closed_ts"] >= cutoff
    flipped.loc[later, "outcome"] = 1 - flipped.loc[later, "outcome"]

    def decisions_before_cutoff(frame):
        trades = walk_forward(frame, cost=0.01, min_train=500)
        return trades[trades["month_start"] <= cutoff].set_index("market_id")["side"].sort_index()

    original = decisions_before_cutoff(df)
    assert len(original) > 100
    pd.testing.assert_series_equal(original, decisions_before_cutoff(flipped))


def test_a_market_already_closed_at_decision_time_is_never_traded():
    df = timed_markets(a=0.0, b=1.4, n=6_000, seed=9)
    closed_early = df.index[-50:]
    df.loc[closed_early, "end_ts"] = df.loc[closed_early, "closed_ts"] + 30 * DAY
    df.loc[closed_early, "price_sched_7d"] = 0.05  # a stray price where none should exist
    trades = walk_forward(df, cost=0.01, min_train=500)
    assert not set(trades["market_id"]) & set(df.loc[closed_early, "market_id"])
