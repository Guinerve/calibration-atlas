"""Headline numbers from the study table."""

from __future__ import annotations

import math

import pandas as pd

from .metrics import brier_score, cluster_bootstrap, murphy_decomposition
from .recalibration import fit_recalibration

Z95 = 1.959964


def _sample(study: pd.DataFrame, horizon: str, exclude_early: bool) -> pd.DataFrame:
    df = study.dropna(subset=[f"price_{horizon}"])
    if exclude_early:
        df = df[~df["resolved_early"].astype(bool)]
    return df


def summarise(study: pd.DataFrame, horizon: str = "7d", exclude_early: bool = False,
              n_boot: int = 1000, seed: int = 0) -> dict:
    df = _sample(study, horizon, exclude_early)
    price, outcome = df[f"price_{horizon}"].to_numpy(), df["outcome"].to_numpy()
    fit = fit_recalibration(df[f"price_{horizon}"], df["outcome"], df["event_id"])
    out = {
        "horizon": horizon,
        "exclude_early": exclude_early,
        "markets": len(df),
        "events": df["event_id"].nunique(),
        "base_rate": float(outcome.mean()),
        **murphy_decomposition(price, outcome, bins=10),
        "a": fit.a, "se_a": fit.se_a, "b": fit.b, "se_b": fit.se_b,
    }
    if n_boot:
        col = f"price_{horizon}"
        out["brier_low"], out["brier_high"] = cluster_bootstrap(
            df, "event_id", lambda d: brier_score(d[col].to_numpy(), d["outcome"].to_numpy()),
            n_boot=n_boot, seed=seed)
    return out


def by_category(study: pd.DataFrame, horizon: str = "7d", exclude_early: bool = False,
                min_markets: int = 300, min_events: int = 0) -> pd.DataFrame:
    """Recalibration slope per category, with a 95% interval clustered by event.
    Categories with fewer than ``min_markets`` markets or ``min_events`` events get no estimate."""
    df = _sample(study, horizon, exclude_early)
    rows = []
    for category, group in df.groupby("category"):
        row = {"category": category, "markets": len(group), "events": group["event_id"].nunique(),
               "b": math.nan, "b_low": math.nan, "b_high": math.nan}
        if len(group) >= min_markets and row["events"] >= min_events:
            fit = fit_recalibration(group[f"price_{horizon}"], group["outcome"], group["event_id"])
            row |= {"b": fit.b, "b_low": fit.b - Z95 * fit.se_b, "b_high": fit.b + Z95 * fit.se_b}
        rows.append(row)
    return pd.DataFrame(rows).sort_values("markets", ascending=False, ignore_index=True)
