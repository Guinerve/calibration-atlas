import numpy as np
import pandas as pd
import pytest

from calibration_atlas.recalibration import fit_recalibration, logit, simulate_markets


@pytest.mark.parametrize("a, b", [(0.0, 1.0), (0.0, 1.3), (-0.2, 0.8)])
def test_fit_recovers_the_bias_it_was_simulated_with(a, b):
    sim = simulate_markets(a=a, b=b, n=40_000, seed=11)
    fit = fit_recalibration(sim["price"], sim["outcome"], sim["event"])
    assert abs(fit.a - a) < 3 * fit.se_a + 0.02
    assert abs(fit.b - b) < 3 * fit.se_b + 0.02


def test_copies_inside_the_same_event_do_not_shrink_the_standard_errors():
    sim = simulate_markets(a=0.0, b=1.2, n=3_000, seed=4)
    copies = pd.concat([sim] * 5, ignore_index=True)
    one = fit_recalibration(sim["price"], sim["outcome"], sim["event"])
    five = fit_recalibration(copies["price"], copies["outcome"], copies["event"])
    assert five.b == pytest.approx(one.b, abs=1e-6)
    assert five.se_b == pytest.approx(one.se_b, rel=0.05)


def test_prices_of_exactly_zero_or_one_do_not_break_the_fit():
    # Outcomes are mixed at every price, so the fit is identifiable; the point is the clipping.
    price = pd.Series([0.0, 0.0, 1.0, 1.0, 0.3, 0.3, 0.7, 0.7] * 25)
    outcome = pd.Series([0, 1, 1, 0, 0, 1, 1, 0] * 25)
    fit = fit_recalibration(price, outcome, pd.Series(range(200)))
    assert np.isfinite(fit.a) and np.isfinite(fit.b)


def test_predict_applies_the_fitted_curve():
    sim = simulate_markets(a=0.0, b=1.0, n=20_000, seed=5)
    fit = fit_recalibration(sim["price"], sim["outcome"], sim["event"])
    assert fit.predict(np.array([0.5]))[0] == pytest.approx(0.5, abs=0.03)
    assert fit.predict(np.array([0.9]))[0] == pytest.approx(0.9, abs=0.03)


def test_simulated_markets_share_events_like_real_multi_outcome_markets():
    sim = simulate_markets(a=0.0, b=1.0, n=1_000, seed=6, markets_per_event=4)
    assert sim["event"].nunique() == 250


def test_prices_below_one_cent_keep_their_own_logit():
    # Polymarket quotes down to 0.05 cents; flattening those to 1 cent biases the slope.
    assert logit(np.array([0.0005]))[0] < logit(np.array([0.001]))[0] < logit(np.array([0.01]))[0]
