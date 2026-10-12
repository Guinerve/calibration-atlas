import numpy as np
import pytest

from calibration_atlas.pooling import pool_slopes


def pooled(b, se, **kwargs):
    names = [f"c{i}" for i in range(len(b))]
    return pool_slopes(names, np.array(b, float), np.array(se, float), **kwargs)


def test_noisy_category_is_pulled_toward_the_others_and_precise_ones_stay_put():
    result = pooled([1.0, 1.02, 0.98, 2.0], [0.02, 0.02, 0.02, 1.0])
    table = result.table.set_index("category")
    assert table.loc["c3", "b_pooled"] < 1.3
    assert table.loc["c0", "b_pooled"] == pytest.approx(1.0, abs=0.02)


def test_agreeing_categories_get_narrower_intervals_than_alone():
    rng = np.random.default_rng(0)
    b = 1.1 + rng.normal(0, 0.02, 6)
    table = pooled(b, [0.1] * 6).table
    alone = 2 * 1.959964 * 0.1
    assert ((table["high"] - table["low"]) < 0.8 * alone).all()


def test_a_real_difference_survives_pooling():
    table = pooled([1.0, 1.7, 0.9, 1.05], [0.03, 0.05, 0.03, 0.04]).table.set_index("category")
    assert table.loc["c1", "b_pooled"] > 1.55
    assert table.loc["c1", "low"] > 1.0


def test_population_mean_and_a_new_category_are_reported():
    result = pooled([1.0, 1.7, 0.9, 1.05], [0.03, 0.05, 0.03, 0.04])
    mu_mean, mu_low, mu_high = result.mu
    _, new_low, new_high = result.new_category
    assert mu_low < mu_mean < mu_high
    assert new_low < mu_low and new_high > mu_high  # a new category is less certain than the mean
    assert result.tau[0] > 0.1  # categories genuinely differ here


def test_results_are_reproducible_with_a_seed():
    a = pooled([1.0, 1.3, 0.9], [0.05, 0.1, 0.05], seed=3).table
    b = pooled([1.0, 1.3, 0.9], [0.05, 0.1, 0.05], seed=3).table
    assert a.equals(b)


def test_pooled_estimates_are_closer_to_the_truth_than_estimates_alone():
    rng = np.random.default_rng(42)
    errors_alone, errors_pooled = [], []
    for _ in range(40):
        truth = rng.normal(1.1, 0.1, 6)
        se = rng.uniform(0.05, 0.3, 6)
        estimate = truth + rng.normal(0, se)
        table = pooled(estimate, se, n_draws=4_000).table
        errors_alone.append(np.mean((estimate - truth) ** 2))
        errors_pooled.append(np.mean((table["b_pooled"] - truth) ** 2))
    assert np.mean(errors_pooled) < 0.7 * np.mean(errors_alone)


def test_closed_form_tau_posterior_matches_a_direct_multivariate_normal():
    from scipy import stats

    from calibration_atlas.pooling import TAU_GRID, _tau_posterior

    y, s = np.array([0.9, 1.7, 1.0, 1.05]), np.array([0.04, 0.23, 0.1, 0.13])
    direct = np.array([
        stats.multivariate_normal.logpdf(y, np.ones(4), np.diag(s**2 + t**2) + 1.0)
        + stats.halfnorm.logpdf(t, scale=0.5) for t in TAU_GRID])
    direct = np.exp(direct - direct.max())
    direct /= direct.sum()
    assert np.abs(_tau_posterior(y, s, 1.0, 1.0, 0.5) - direct).max() < 1e-12
