import numpy as np
import pandas as pd
import pytest

from calibration_atlas.metrics import (
    brier_score,
    cluster_bootstrap,
    murphy_decomposition,
    reliability_table,
)


def test_brier_score_is_mean_squared_error():
    assert brier_score(np.array([0.8, 0.3]), np.array([1, 0])) == pytest.approx((0.04 + 0.09) / 2)


def test_murphy_components_add_up_to_the_brier_score_when_forecasts_sit_on_bins():
    rng = np.random.default_rng(0)
    p = rng.choice([0.05, 0.25, 0.55, 0.85], size=4_000)
    y = (rng.random(4_000) < p).astype(int)
    d = murphy_decomposition(p, y, bins=10)
    assert d["reliability"] - d["resolution"] + d["uncertainty"] == pytest.approx(brier_score(p, y))


def test_calibrated_forecasts_have_near_zero_reliability_term():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.02, 0.98, size=50_000)
    y = (rng.random(50_000) < p).astype(int)
    assert murphy_decomposition(p, y, bins=10)["reliability"] < 0.001


def test_reliability_table_reports_each_bin():
    p = np.array([0.05, 0.08, 0.92, 0.95])
    y = np.array([0, 1, 1, 1])
    table = reliability_table(p, y, bins=10)
    low = table.iloc[0]
    assert (low["count"], low["mean_forecast"], low["observed"]) == (2, pytest.approx(0.065), 0.5)
    assert table["count"].sum() == 4
    assert list(table["bin_low"]) == [0.0, 0.9]


def test_duplicating_rows_inside_clusters_does_not_narrow_the_cluster_bootstrap():
    rng = np.random.default_rng(2)
    base = pd.DataFrame({"event": range(60), "x": rng.normal(size=60)})
    doubled = pd.concat([base, base], ignore_index=True)

    def mean_x(df):
        return df["x"].mean()

    assert cluster_bootstrap(doubled, "event", mean_x, n_boot=300, seed=7) == pytest.approx(
        cluster_bootstrap(base, "event", mean_x, n_boot=300, seed=7))


def test_cluster_bootstrap_interval_contains_the_point_estimate():
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"event": rng.integers(0, 40, 400), "x": rng.normal(1.0, 1.0, 400)})
    low, high = cluster_bootstrap(df, "event", lambda d: d["x"].mean(), n_boot=500, seed=1)
    assert low < df["x"].mean() < high
