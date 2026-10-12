"""Bayesian partial pooling of the category slopes.

Each category's slope b is estimated alone, with an event clustered standard error.
The hierarchical model treats the true slopes as draws from a common distribution:

    b_hat[c] ~ Normal(b[c], se[c])      (the estimate, with its clustered error)
    b[c]     ~ Normal(mu, tau)          (categories differ by tau around mu)
    mu       ~ Normal(1, 1)             (centred on calibrated)
    tau      ~ HalfNormal(0.5)

A category with a noisy estimate borrows strength from the others; one with a precise
estimate keeps it. Because mu has a conjugate prior, the posterior of tau is computed
exactly on a grid and the rest is drawn from closed form normals: no MCMC, no tuning,
and it runs in well under a second. Working from the clustered errors, rather than
individual markets, keeps the correlation between markets in one event accounted for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

TAU_GRID = np.linspace(1e-4, 3.0, 3_000)


@dataclass
class PooledSlopes:
    table: pd.DataFrame  # category, b_alone, se_alone, b_pooled, low, high
    mu: tuple[float, float, float]  # pooled mean slope: mean, low, high
    tau: tuple[float, float, float]  # spread between categories: median, low, high
    new_category: tuple[float, float, float]  # what an unseen category's slope could be


def _tau_posterior(y, s, prior_mean, prior_sd, tau_sd):
    """p(tau | data) on TAU_GRID, with mu integrated out. The marginal covariance is
    diag(s^2 + tau^2) + prior_sd^2, so its inverse and determinant have closed forms."""
    d = s[None, :] ** 2 + TAU_GRID[:, None] ** 2
    r = y - prior_mean
    c = prior_sd**2
    k = 1 + c * (1 / d).sum(axis=1)
    quad = (r**2 / d).sum(axis=1) - c * (r / d).sum(axis=1) ** 2 / k
    log_det = np.log(d).sum(axis=1) + np.log(k)
    log_post = -0.5 * (quad + log_det) + stats.halfnorm.logpdf(TAU_GRID, scale=tau_sd)
    weights = np.exp(log_post - log_post.max())
    return weights / weights.sum()


def pool_slopes(categories: Sequence[str], b: np.ndarray, se: np.ndarray, *,
                prior_mean: float = 1.0, prior_sd: float = 1.0, tau_sd: float = 0.5,
                level: float = 0.95, n_draws: int = 40_000, seed: int = 0) -> PooledSlopes:
    y, s = np.asarray(b, float), np.asarray(se, float)
    rng = np.random.default_rng(seed)
    tau = rng.choice(TAU_GRID, size=n_draws, p=_tau_posterior(y, s, prior_mean, prior_sd, tau_sd))

    # mu | tau, data: normal (conjugate prior)
    w = 1 / (s[None, :] ** 2 + tau[:, None] ** 2)
    v_mu = 1 / (1 / prior_sd**2 + w.sum(axis=1))
    m_mu = v_mu * (prior_mean / prior_sd**2 + (w * y).sum(axis=1))
    mu = rng.normal(m_mu, np.sqrt(v_mu))

    # b[c] | mu, tau, data: precision weighted blend of the estimate and mu
    precision = 1 / s[None, :] ** 2 + 1 / tau[:, None] ** 2
    mean = (y / s**2 + mu[:, None] / tau[:, None] ** 2) / precision
    draws = rng.normal(mean, np.sqrt(1 / precision))
    new = rng.normal(mu, tau)

    q = [(1 - level) / 2, 1 - (1 - level) / 2]
    low, high = np.quantile(draws, q, axis=0)
    table = pd.DataFrame({"category": list(categories), "b_alone": y, "se_alone": s,
                          "b_pooled": draws.mean(axis=0), "low": low, "high": high})

    def summary(x, centre):
        lo, hi = np.quantile(x, q)
        return float(centre(x)), float(lo), float(hi)

    return PooledSlopes(table=table, mu=summary(mu, np.mean), tau=summary(tau, np.median),
                        new_category=summary(new, np.mean))
