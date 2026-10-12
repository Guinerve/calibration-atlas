"""calatlas command line."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .collect import collect
from .fetch import Fetcher


def cmd_collect(args: argparse.Namespace) -> int:
    fetcher = Fetcher(cache_dir=args.data / "raw")
    summary = collect(fetcher, max_events=args.max_events, out_dir=args.data, workers=args.workers)
    print(f"{summary['events']} events, {summary['markets']} eligible markets, "
          f"{summary['rows']} rows written, {summary['errors']} failed (see errors.csv)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    study_path = args.data / "study.csv"
    study = pd.read_csv(study_path, dtype={"market_id": str, "event_id": str})
    meta_path = args.data / "collection.json"
    if meta_path.exists():
        downloaded = datetime.fromisoformat(json.loads(meta_path.read_text())["collected"])
    else:  # older collections: the file time is the best guess, and survives only locally
        downloaded = datetime.fromtimestamp(study_path.stat().st_mtime, UTC)
    from .explorer import export_markets
    from .report import build_report

    note = f"Polymarket public data collected {downloaded:%d %B %Y}"
    build_report(study, out_dir=args.out, data_note=note, n_boot=args.n_boot)
    export_markets(study, args.site / "data" / "markets.json", data_note=note)
    print(f"Wrote {args.out / 'REPORT.md'}, charts in {args.out / 'figures'}, "
          f"and explorer data in {args.site / 'data'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="calatlas", description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("collect", help="download resolved markets and build data/study.csv")
    p.add_argument("--max-events", type=int, default=2_000)
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("report", help="analyse data/study.csv and write the report and charts")
    p.add_argument("--out", type=Path, default=Path("reports"))
    p.add_argument("--n-boot", type=int, default=1000)
    p.add_argument("--site", type=Path, default=Path("docs"), help="explorer site folder")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)
