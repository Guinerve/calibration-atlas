"""Collect the study table from the API (or the cache)."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from .dataset import candidate_markets, decision_price, snapshot


def collect(fetcher, max_events: int, out_dir: Path, workers: int = 4) -> dict[str, int]:
    """Write study.csv (one row per market) and errors.csv (markets that failed to download)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events = list(fetcher.closed_events(max_events=max_events))
    markets = [m for event in events for m in candidate_markets(event)]

    def one(m: dict) -> tuple[dict | None, dict | None]:
        try:
            history = fetcher.history(m["yes_token"], closed_ts=m["closed_ts"])
        except Exception as exc:  # noqa: BLE001 - any failure is recorded in errors.csv
            return None, {"market_id": m["market_id"], "error": f"{type(exc).__name__}: {exc}"}
        return m | snapshot(m["closed_ts"], history) | {
            "price_sched_7d": decision_price(m["closed_ts"], m["end_ts"], history),
            "history_points": len(history)}, None

    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (row, error) in enumerate(pool.map(one, markets), 1):
            if row is not None:
                rows.append(row)
            if error is not None:
                errors.append(error)
            if i % 250 == 0:
                print(f"  {i}/{len(markets)} markets", file=sys.stderr, flush=True)

    pd.DataFrame(rows).to_csv(out_dir / "study.csv", index=False)
    pd.DataFrame(errors, columns=["market_id", "error"]).to_csv(out_dir / "errors.csv", index=False)
    return {"events": len(events), "markets": len(markets), "rows": len(rows), "errors": len(errors)}
