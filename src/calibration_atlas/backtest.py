"""Walk-forward test of trading on the recalibration.

Each month the recalibration is refitted using only markets that had already
resolved before the month began, then applied to markets whose decision time
(7 days before their scheduled end) falls in that month. A trade is placed when
the recalibrated probability beats the price by more than the trading cost.

The decision time comes from the scheduled end because the actual close is not
known in advance: timing trades from it would quietly peek at early resolutions.
``timing="close"`` runs that leaky version, kept only to show how much it flatters.
"""

from __future__ import annotations

import pandas as pd

from .dataset import DECISION_BEFORE_END
from .recalibration import fit_recalibration


def trade_pnl(side: str, price: float, outcome: int, cost: float) -> float:
    """Profit on a $1-payout contract: buy Yes at price + cost, or No at (1 - price) + cost."""
    if side == "yes":
        return outcome - (price + cost)
    return (1 - outcome) - (1 - price + cost)


def _month_start(ts: pd.Series) -> pd.Series:
    month = pd.to_datetime(ts, unit="s", utc=True).dt.tz_localize(None).dt.to_period("M")
    return (month.dt.start_time - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)


# timing -> (price column, the timestamp the decision is measured back from)
TIMINGS = {"scheduled": ("price_sched_7d", "end_ts"), "close": ("price_7d", "closed_ts")}


def walk_forward(df: pd.DataFrame, cost: float = 0.01, min_train: int = 500,
                 threshold: float = 0.0, timing: str = "scheduled") -> pd.DataFrame:
    price_col, anchor = TIMINGS[timing]
    data = df.dropna(subset=[price_col]).copy()
    decision_ts = data[anchor] - DECISION_BEFORE_END
    if timing == "scheduled":
        data = data[data["closed_ts"] > decision_ts]  # still open, so actually tradable
        decision_ts = decision_ts[data.index]
    data["month_start"] = _month_start(decision_ts)

    trades = []
    for month in sorted(data["month_start"].unique()):
        known = data[data["closed_ts"] < month]  # outcomes already public when the month began
        if len(known) < min_train:
            continue
        fit = fit_recalibration(known[price_col], known["outcome"], known["event_id"])
        current = data[data["month_start"] == month]
        q = fit.predict(current[price_col].to_numpy())
        price = current[price_col].to_numpy()
        for row, p, qi in zip(current.itertuples(index=False), price, q, strict=True):
            if qi - p > cost + threshold:
                side = "yes"
            elif p - qi > cost + threshold:
                side = "no"
            else:
                continue
            trades.append({"market_id": row.market_id, "event_id": row.event_id,
                           "month_start": int(month), "side": side, "price": float(p),
                           "q": float(qi), "outcome": int(row.outcome),
                           "pnl": trade_pnl(side, float(p), int(row.outcome), cost)})
    return pd.DataFrame(trades, columns=["market_id", "event_id", "month_start", "side",
                                         "price", "q", "outcome", "pnl"])
