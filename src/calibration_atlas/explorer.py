"""Data for the interactive explorer (docs/index.html), as compact JSON columns."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

PRICE_COLUMNS = {"30d": "price_30d", "7d": "price_7d", "1d": "price_1d", "sched_7d": "price_sched_7d"}


def _prices(series: pd.Series) -> list[float | None]:
    return [None if math.isnan(p) else round(float(p), 4) for p in series]


def export_markets(study: pd.DataFrame, path: Path, data_note: str) -> None:
    categories = sorted(study["category"].unique())
    events = {e: i for i, e in enumerate(dict.fromkeys(study["event_id"]))}
    data = {
        "note": data_note,
        "categories": categories,
        "category": [categories.index(c) for c in study["category"]],
        "event": [events[e] for e in study["event_id"]],
        "outcome": [int(o) for o in study["outcome"]],
        "early": [int(bool(e)) for e in study["resolved_early"]],
        "volume": [round(float(v)) for v in study["volume"]],
        "price": {name: _prices(study[col]) for name, col in PRICE_COLUMNS.items()},
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
