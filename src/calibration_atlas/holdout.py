"""The pre-registered holdout: the macro slope, on markets that closed after the collection.

``collect_holdout`` downloads every event that closed after the original collection,
keeps the macro markets under the frozen rules, and records the price 7 days before each
one's scheduled end. ``evaluate`` reads the test exactly as PROTOCOL.md says: blinded
(counts only) until the first MIN_EVENTS events have closed, then on those events alone,
so later data cannot move the verdict.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from scipy import stats

from . import protocol as P
from .analysis import Z95
from .dataset import DECISION_BEFORE_END, candidate_markets, decision_price
from .markets import parse_time
from .recalibration import fit_recalibration

Z_ONE_SIDED = float(stats.norm.ppf(1 - P.ALPHA))
DAY = 86_400
COLUMNS = ["market_id", "event_id", "question", "category", "tags", "yes_token", "outcome",
           "volume", "closed_ts", "end_ts", "resolved_early", "neg_risk", "event_volume",
           "event_closed_ts", "price_sched_7d"]


def holdout_markets(event: dict) -> list[dict]:
    """The event's markets that meet the frozen rules, closed after the cutoff, in the
    hypothesis category, and still open at their decision time (else there is no price)."""
    closed = parse_time(event.get("closedTime"))
    if closed is None or closed.timestamp() <= P.CUTOFF_TS:
        return []
    extra = {"event_volume": float(event.get("volume") or 0),
             "event_closed_ts": int(closed.timestamp())}
    return [m | extra for m in candidate_markets(event)
            if m["category"] == P.HYPOTHESIS["category"] and m["closed_ts"] > P.CUTOFF_TS
            and m["closed_ts"] > m["end_ts"] - DECISION_BEFORE_END]


def collect_holdout(fetcher, out_dir: Path, workers: int = 4,
                    now: datetime | None = None) -> dict:
    """Write holdout.csv, holdout-errors.csv and holdout.json to ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = now or datetime.now(UTC)
    seen, candidates = set(), []
    for event in fetcher.closed_since(P.CUTOFF_TS, min_volume=P.SECONDARY_MIN_EVENT_VOLUME):
        if event["id"] not in seen:
            seen.add(event["id"])
            candidates += holdout_markets(event)

    def one(m: dict) -> tuple[dict | None, dict | None]:
        try:
            history = fetcher.history(m["yes_token"], closed_ts=m["closed_ts"])
        except Exception as exc:  # noqa: BLE001 - any failure is recorded in holdout-errors.csv
            return None, {"market_id": m["market_id"], "error": f"{type(exc).__name__}: {exc}"}
        return m | {"price_sched_7d": decision_price(m["closed_ts"], m["end_ts"], history)}, None

    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (row, error) in enumerate(pool.map(one, candidates), 1):
            if row is not None:
                rows.append(row)
            if error is not None:
                errors.append(error)
            if i % 250 == 0:
                print(f"  {i}/{len(candidates)} markets", file=sys.stderr, flush=True)

    pd.DataFrame(rows, columns=COLUMNS).to_csv(out_dir / "holdout.csv", index=False)
    pd.DataFrame(errors, columns=["market_id", "error"]).to_csv(
        out_dir / "holdout-errors.csv", index=False)
    meta = {"collected_at": started.isoformat(timespec="seconds"), "events_listed": len(seen),
            "markets": len(candidates), "rows": len(rows), "errors": len(errors)}
    (out_dir / "holdout.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def _population(holdout: pd.DataFrame, min_event_volume: float, study_ids: set[str],
                as_of: datetime) -> pd.DataFrame:
    settled_by = as_of.timestamp() - P.SETTLE_DAYS * DAY
    df = holdout[(holdout["category"] == P.HYPOTHESIS["category"])
                 & (holdout["closed_ts"] > P.CUTOFF_TS)
                 & (holdout["event_closed_ts"] > P.CUTOFF_TS)
                 & (holdout["event_closed_ts"] <= settled_by)
                 & (holdout["event_volume"] >= min_event_volume)
                 & ~holdout["market_id"].isin(study_ids)]
    return df.dropna(subset=[P.HYPOTHESIS["price"]])


def _event_order(df: pd.DataFrame) -> list[str]:
    first = df.groupby("event_id")["event_closed_ts"].first()
    return list(first.sort_values(kind="stable").index)


def _fit(df: pd.DataFrame) -> dict:
    out = {"markets": len(df), "events": df["event_id"].nunique(),
           "yes_rate": float(df["outcome"].mean()) if len(df) else float("nan")}
    if len(df) < 30 or df["outcome"].nunique() < 2 or out["events"] < 3:
        return out | {"b": None}
    fit = fit_recalibration(df[P.HYPOTHESIS["price"]], df["outcome"], df["event_id"])
    return out | {"a": fit.a, "b": fit.b, "se_b": fit.se_b,
                  "low": fit.b - Z95 * fit.se_b, "high": fit.b + Z95 * fit.se_b,
                  "one_sided_low": fit.b - Z_ONE_SIDED * fit.se_b}


def verdict(result: dict) -> str:
    if result.get("b") is None:
        return "no stable fit"
    if result["one_sided_low"] > 1:
        return "supported"
    if result["high"] < 1:
        return "reversed"
    return "not supported"


def power(true_b: float, events: int = P.MIN_EVENTS) -> float:
    """Chance of a 'supported' verdict if the true slope is ``true_b``, assuming the standard
    error shrinks with the square root of the number of events from the original's."""
    se = (P.ORIGINAL["high"] - P.ORIGINAL["low"]) / (2 * Z95) * (P.ORIGINAL["events"] / events) ** 0.5
    return float(stats.norm.cdf((true_b - 1) / se - Z_ONE_SIDED))


def evaluate(holdout: pd.DataFrame, study_ids: set[str], as_of: datetime) -> dict:
    """Blinded counts, or the read test. ``as_of`` is when the holdout was collected."""
    holdout = holdout.astype({"market_id": str, "event_id": str})
    primary = _population(holdout, P.PRIMARY_MIN_EVENT_VOLUME, study_ids, as_of)
    secondary = _population(holdout, P.SECONDARY_MIN_EVENT_VOLUME, study_ids, as_of)
    order = _event_order(primary)
    closes = primary.groupby("event_id")["event_closed_ts"].first()
    by_deadline = [e for e in order if closes[e] <= P.DEADLINE.timestamp()]
    out = {"as_of": as_of.isoformat(timespec="seconds"), "fingerprint": P.fingerprint(),
           "progress": {"primary": {"events": len(order), "markets": len(primary)},
                        "secondary": {"events": secondary["event_id"].nunique(),
                                      "markets": len(secondary)}},
           "needed": P.MIN_EVENTS, "deadline": P.DEADLINE.date().isoformat()}
    if len(by_deadline) >= P.MIN_EVENTS:
        confirm, status = by_deadline[: P.MIN_EVENTS], "read"
    elif as_of >= P.DEADLINE:
        confirm, status = by_deadline, "read, underpowered"
    else:
        return out | {"status": "blinded"}
    sample = primary[primary["event_id"].isin(confirm)]
    through = int(sample["event_closed_ts"].max()) if len(sample) else P.CUTOFF_TS
    results = {"primary": _fit(sample),
               "secondary": _fit(secondary[secondary["event_closed_ts"] <= through])}
    for r in results.values():
        r["verdict"] = verdict(r)
    return out | {"status": status, "through": datetime.fromtimestamp(through, UTC).isoformat(),
                  "results": results}


def _date(iso: str) -> str:
    return f"{datetime.fromisoformat(iso):%d %B %Y}"


def write_holdout_report(result: dict, path: Path) -> None:
    o = P.ORIGINAL
    prog = result["progress"]
    lines = [
        "# Holdout test: the macro slope on new markets",
        "",
        (f"Status at {datetime.fromisoformat(result['as_of']):%d %B %Y %H:%M} UTC: "
         f"**{result['status']}**. Regenerated by "
         "`calatlas holdout` (downloads new markets) or `calatlas report` (from the saved data)."),
        "",
        "## The claim under test",
        "",
        (f"In the original sample, finance and macro markets priced 7 days before their scheduled "
         f"end had a recalibration slope of **b = {o['b']:.2f}** ({o['low']:.2f} to "
         f"{o['high']:.2f}), from {o['markets']} markets in {o['events']} events; partial pooling "
         f"shrank it to {o['pooled']:.2f}. That pattern was found after looking at the data, so "
         "it is tested here on markets that **closed after the collection**, under rules frozen "
         f"on {_date(P.FROZEN_ON)} ([PROTOCOL.md](../PROTOCOL.md))."),
        "",
        "## Pre-registered design",
        "",
        f"- **New data only**: markets that closed after {P.CUTOFF:%d %B %Y %H:%M} UTC.",
        (f"- **Primary population**: events with at least ${P.PRIMARY_MIN_EVENT_VOLUME:,} traded, "
         "the size of the smallest event in the original sample. **Secondary**: every event, "
         f"markets still need ${P.SECONDARY_MIN_EVENT_VOLUME:,} each."),
        (f"- **Read once**, on the first {P.MIN_EVENTS} primary events to close (the original's "
         "size); until then this page shows counts, never the slope. If that count is not "
         f"reached by {P.DEADLINE:%d %B %Y}, the test is read on what there is and labelled "
         "underpowered."),
        (f"- **Verdict**: *supported* if the one sided {1 - P.ALPHA:.0%} lower bound on b is "
         "above 1; *reversed* if the two sided 95% interval lies below 1; otherwise *not "
         "supported*. Errors are clustered by event."),
        (f"- **Power**: about {power(o['b']):.0%} if the true slope is the original {o['b']:.2f}, "
         f"and about {power(o['pooled']):.0%} if it is the pooled {o['pooled']:.2f}. A *not "
         "supported* verdict mostly rules out an effect as large as first measured; it is weak "
         "evidence that macro prices are calibrated."),
        "",
        "## Progress",
        "",
        "| Population | Events | Markets | Needed to read |",
        "|---|--:|--:|--:|",
        (f"| Primary (events ≥ ${P.PRIMARY_MIN_EVENT_VOLUME / 1e6:.2f}M) | "
         f"{prog['primary']['events']:,} | {prog['primary']['markets']:,} | {P.MIN_EVENTS} events |"),
        (f"| Secondary (all events) | {prog['secondary']['events']:,} | "
         f"{prog['secondary']['markets']:,} | read with the primary |"),
        "",
    ]
    if result["status"] == "blinded":
        lines += [
            ("The slope stays hidden until the primary population reaches its size, so that no "
             "one, including the author, can stop the test early on a convenient result."),
            "",
        ]
    else:
        lines += [
            "## Result",
            "",
            f"Confirmatory sample: events that closed up to {_date(result['through'])}.",
            "",
            "| Population | Markets | Events | b (95% CI) | One sided lower bound | Verdict |",
            "|---|--:|--:|---|--:|---|",
        ]
        for name, r in result["results"].items():
            if r.get("b") is None:
                lines.append(f"| {name} | {r['markets']:,} | {r['events']:,} | – | – | {r['verdict']} |")
            else:
                lines.append(
                    f"| {name} | {r['markets']:,} | {r['events']:,} | {r['b']:.2f} "
                    f"({r['low']:.2f} to {r['high']:.2f}) | {r['one_sided_low']:.2f} | "
                    f"**{r['verdict']}** |")
        lines.append("")
    lines += [f"Protocol fingerprint: `{result['fingerprint']}`", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def export_status(result: dict, path: Path) -> None:
    """The explorer's holdout banner reads this; it never contains a blinded slope."""
    keep = {k: result[k] for k in ("status", "as_of", "progress", "needed", "deadline")}
    if "results" in result:
        keep["results"] = {k: {f: v[f] for f in ("b", "low", "high", "events", "verdict") if f in v}
                           for k, v in result["results"].items()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keep, indent=2) + "\n", encoding="utf-8")
