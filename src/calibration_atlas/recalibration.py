"""Logistic recalibration: logit(P(outcome)) = a + b * logit(price).

a = 0 and b = 1 means prices are calibrated. b > 1 means prices are too timid at
the extremes: favourites win more often, and long shots less often, than their
prices say (the classic favourite–longshot pattern). b < 1 means prices are
overconfident. a shifts everything towards Yes (a > 0) or No (a < 0).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm

# Prices are clipped so their logits stay finite. 0.0005 is the smallest price Polymarket
# publishes (half its 0.1 cent tick), so real prices pass through unchanged; a 1 cent clip
# flattened the many sub cent long shots together and inflated the slope.
CLIP = 0.0005


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, float), CLIP, 1 - CLIP)
    return np.log(p / (1 - p))


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.asarray(x, float)))


@dataclass(frozen=True)
class Recalibration:
    a: float
    b: float
    se_a: float  # standard errors clustered by event
    se_b: float
    n: int
    n_events: int

    def predict(self, price: np.ndarray) -> np.ndarray:
        return sigmoid(self.a + self.b * logit(price))


def fit_recalibration(price: pd.Series, outcome: pd.Series, event: pd.Series) -> Recalibration:
    """Maximum-likelihood fit with standard errors clustered by event."""
    x = sm.add_constant(logit(price.to_numpy()), has_constant="add")
    groups = pd.factorize(event)[0]
    result = sm.GLM(outcome.to_numpy(), x, family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": groups})
    (a, b), (se_a, se_b) = result.params, result.bse
    return Recalibration(float(a), float(b), float(se_a), float(se_b),
                         n=len(price), n_events=int(groups.max()) + 1)


def simulate_markets(a: float, b: float, n: int, seed: int = 0,
                     markets_per_event: int = 1) -> pd.DataFrame:
    """Markets whose outcomes follow a known recalibration curve, for recovery tests."""
    rng = np.random.default_rng(seed)
    price = np.clip(sigmoid(rng.normal(0, 1.5, n)), CLIP, 1 - CLIP)
    outcome = (rng.random(n) < sigmoid(a + b * logit(price))).astype(int)
    return pd.DataFrame({"price": price, "outcome": outcome,
                         "event": np.arange(n) // markets_per_event})
