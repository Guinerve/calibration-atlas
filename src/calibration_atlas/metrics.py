"""Calibration statistics."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd


def brier_score(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def _bin_index(p: np.ndarray, bins: int) -> np.ndarray:
    return np.minimum((np.asarray(p, float) * bins).astype(int), bins - 1)


def reliability_table(p: np.ndarray, y: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """Per non-empty bin of forecast probability: count, mean forecast, observed frequency."""
    df = pd.DataFrame({"bin": _bin_index(p, bins), "p": p, "y": y})
    table = df.groupby("bin").agg(count=("y", "size"), mean_forecast=("p", "mean"),
                                  observed=("y", "mean")).reset_index()
    table["bin_low"] = table["bin"] / bins
    table["bin_high"] = (table["bin"] + 1) / bins
    return table[["bin_low", "bin_high", "count", "mean_forecast", "observed"]]


def murphy_decomposition(p: np.ndarray, y: np.ndarray, bins: int = 10) -> dict[str, float]:
    """Brier score = reliability - resolution + uncertainty (+ a within-bin term).

    reliability: how far forecasts sit from what happened (lower is better).
    resolution:  how much forecasts separate outcomes from the base rate (higher is better).
    uncertainty: the base rate's own variance, outside the forecaster's control.
    within_bin:  the remainder from forecasts that vary inside a bin (0 if they don't).
    """
    p, y = np.asarray(p, float), np.asarray(y, float)
    table = reliability_table(p, y, bins)
    n, base_rate = len(y), y.mean()
    reliability = float((table["count"] * (table["mean_forecast"] - table["observed"]) ** 2).sum() / n)
    resolution = float((table["count"] * (table["observed"] - base_rate) ** 2).sum() / n)
    uncertainty = float(base_rate * (1 - base_rate))
    return {
        "brier": brier_score(p, y),
        "reliability": reliability,
        "resolution": resolution,
        "uncertainty": uncertainty,
        "within_bin": brier_score(p, y) - (reliability - resolution + uncertainty),
    }


def cluster_bootstrap(df: pd.DataFrame, cluster: str, statistic: Callable[[pd.DataFrame], float],
                      n_boot: int = 1000, seed: int = 0,
                      level: float = 0.95) -> tuple[float, float]:
    """Percentile interval for ``statistic``, resampling whole clusters with replacement.

    Markets on the same event (twenty candidates in one election) are not independent,
    so resampling rows would make intervals look far tighter than the evidence allows.
    """
    rng = np.random.default_rng(seed)
    positions = [np.asarray(idx) for _, idx in
                 sorted(df.groupby(cluster).indices.items(), key=lambda kv: kv[0])]
    k = len(positions)
    values = []
    for _ in range(n_boot):
        chosen = rng.integers(0, k, k)
        rows = np.concatenate([positions[i] for i in chosen])
        values.append(statistic(df.iloc[rows]))
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(values, [tail, 100 - tail])
    return float(low), float(high)
