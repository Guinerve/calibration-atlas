"""calatlas: rebuild the Polymarket calibration study, its report and its holdout test."""

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
    if (args.data / "holdout.csv").exists():
        _holdout_outputs(args, study)
    return 0


def _holdout_outputs(args: argparse.Namespace, study: pd.DataFrame) -> dict:
    """Evaluate the saved holdout as of its collection time, and write its page and status."""
    from .holdout import evaluate, export_status, write_holdout_report

    holdout = pd.read_csv(args.data / "holdout.csv", dtype={"market_id": str, "event_id": str})
    as_of = datetime.fromisoformat(json.loads((args.data / "holdout.json").read_text())["collected_at"])
    result = evaluate(holdout, set(study["market_id"]), as_of=as_of)
    write_holdout_report(result, args.out / "HOLDOUT.md")
    export_status(result, args.site / "data" / "holdout.json")
    prog = result["progress"]["primary"]
    print(f"Holdout {result['status']}: {prog['events']}/{result['needed']} primary events "
          f"({prog['markets']} markets). Wrote {args.out / 'HOLDOUT.md'}")
    return result


def cmd_holdout(args: argparse.Namespace) -> int:
    from .holdout import collect_holdout

    fetcher = Fetcher(cache_dir=args.data / "raw")
    meta = collect_holdout(fetcher, out_dir=args.data, workers=args.workers)
    print(f"{meta['events_listed']} events closed since the cutoff, {meta['rows']} macro markets "
          f"kept, {meta['errors']} failed (see holdout-errors.csv)")
    study = pd.read_csv(args.data / "study.csv", dtype={"market_id": str, "event_id": str})
    _holdout_outputs(args, study)
    return 0


def cmd_fingerprint(args: argparse.Namespace) -> int:
    from .protocol import fingerprint

    print(fingerprint())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="calatlas", description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"),
                        help="folder with study.csv and holdout.csv (default: data)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("collect", help="download resolved markets and build data/study.csv "
                                       "(needs the network)")
    p.add_argument("--max-events", type=int, default=2_000,
                   help="how many closed events to read, most traded first (the study used 1500)")
    p.add_argument("--workers", type=int, default=4, help="parallel downloads")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("report", help="analyse data/study.csv and write the reports, charts and "
                                      "explorer data (no network)")
    p.add_argument("--out", type=Path, default=Path("reports"))
    p.add_argument("--n-boot", type=int, default=1000, help="bootstrap resamples per interval")
    p.add_argument("--site", type=Path, default=Path("docs"), help="explorer site folder")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("holdout", help="download markets closed since the collection and run "
                                       "the macro test fixed in PROTOCOL.md")
    p.add_argument("--workers", type=int, default=4, help="parallel downloads")
    p.add_argument("--out", type=Path, default=Path("reports"))
    p.add_argument("--site", type=Path, default=Path("docs"), help="explorer site folder")
    p.set_defaults(func=cmd_holdout)

    p = sub.add_parser("fingerprint", help="print the protocol fingerprint of the current rules")
    p.set_defaults(func=cmd_fingerprint)

    args = parser.parse_args(argv)
    return args.func(args)
