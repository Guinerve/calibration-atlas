import numpy as np
import pandas as pd
import pytest

from calibration_atlas.analysis import by_category, summarise
from calibration_atlas.recalibration import simulate_markets


def study(b=1.3, n=8_000, seed=0):
    sim = simulate_markets(a=0.0, b=b, n=n, seed=seed, markets_per_event=4)
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "market_id": [f"m{i}" for i in range(n)],
        "event_id": sim["event"].astype(str),
        "outcome": sim["outcome"],
        "price_7d": sim["price"],
        "category": rng.choice(["sports", "politics", "crypto"], n, p=[0.6, 0.38, 0.02]),
        "resolved_early": rng.random(n) < 0.3,
    })


def test_summary_reports_sample_size_scores_and_the_recalibration():
    s = summarise(study(b=1.3), horizon="7d", n_boot=0)
    assert s["markets"] == 8_000 and s["events"] == 2_000
    assert s["brier"] == pytest.approx(s["reliability"] - s["resolution"] + s["uncertainty"]
                                       + s["within_bin"])
    assert abs(s["b"] - 1.3) < 3 * s["se_b"] + 0.02


def test_summary_can_leave_out_markets_that_resolved_early():
    df = study()
    s = summarise(df, horizon="7d", exclude_early=True, n_boot=0)
    assert s["markets"] == (~df["resolved_early"]).sum()


def test_summary_skips_markets_without_a_price_at_the_horizon():
    df = study()
    df.loc[df.index[:1_000], "price_7d"] = np.nan
    assert summarise(df, horizon="7d", n_boot=0)["markets"] == 7_000


def test_summary_gives_an_event_clustered_interval_for_the_brier_score():
    s = summarise(study(), horizon="7d", n_boot=200)
    assert s["brier_low"] < s["brier"] < s["brier_high"]


def test_categories_with_too_few_markets_get_no_estimate():
    table = by_category(study(), horizon="7d", min_markets=500).set_index("category")
    assert table.loc["crypto", "b"] != table.loc["crypto", "b"]  # NaN: too few markets
    assert np.isfinite(table.loc["sports", "b"])
    assert table.loc["sports", "b_low"] < table.loc["sports", "b"] < table.loc["sports", "b_high"]
    assert list(table.index) == ["sports", "politics", "crypto"]  # largest first
