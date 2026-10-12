"""Charts and REPORT.md, generated from the study table so every number is reproducible."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .analysis import by_category, summarise
from .backtest import walk_forward
from .dataset import MIN_VOLUME
from .metrics import cluster_bootstrap, reliability_table

HORIZON_NAMES = {"30d": "30 days before close", "7d": "7 days before close",
                 "1d": "1 day before close"}
# The honest decision time used by the backtest: 7 days before the scheduled end, for
# markets still open then. Known in advance, unlike the actual close.
DECISION = "sched_7d"
TABLE_NAMES = HORIZON_NAMES | {DECISION: "7 days before scheduled end"}
BACKTEST = {"cost": 0.01, "min_train": 500}
TIMING_LABELS = {"scheduled": "Timed from the scheduled end (honest)",
                 "close": "Timed from the actual close (peeks at the future)"}

# Validated categorical slots 1-2 (blue, orange) and text/surface roles, per theme.
THEMES = {
    "light": {"surface": "#fcfcfb", "text": "#0b0b0b", "muted": "#52514e", "grid": "#e6e5e1",
              "series": ["#2a78d6", "#eb6834"]},
    "dark": {"surface": "#1a1a19", "text": "#f0efec", "muted": "#c3c2b7", "grid": "#3a3a37",
             "series": ["#3987e5", "#d95926"]},
}


def _style(ax, theme):
    t = THEMES[theme]
    ax.set_facecolor(t["surface"])
    ax.grid(True, color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(t["grid"])
    ax.tick_params(colors=t["muted"], labelsize=9)
    ax.xaxis.label.set_color(t["muted"])
    ax.yaxis.label.set_color(t["muted"])


def _figure(theme, **kwargs):
    fig, axes = plt.subplots(**kwargs)
    fig.patch.set_facecolor(THEMES[theme]["surface"])
    return fig, axes


def _save(fig, path):
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def chart_reliability(study, path, theme):
    t = THEMES[theme]
    fig, axes = _figure(theme, ncols=3, figsize=(12, 4.3), sharey=True)
    for ax, horizon in zip(axes, HORIZON_NAMES, strict=True):
        _style(ax, theme)
        ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1, color=t["muted"],
                label="Perfect calibration")
        df = study.dropna(subset=[f"price_{horizon}"])
        samples = [("All markets", df), ("Excluding early resolutions", df[~df["resolved_early"]])]
        for (label, sample), color in zip(samples, t["series"], strict=True):
            table = reliability_table(sample[f"price_{horizon}"].to_numpy(),
                                      sample["outcome"].to_numpy(), bins=10)
            ax.plot(table["mean_forecast"], table["observed"], color=color, linewidth=2,
                    marker="o", markersize=5, label=label)
        ax.set_title(HORIZON_NAMES[horizon], fontsize=11, loc="left", color=t["text"])
        ax.set_xlim(0, 1), ax.set_ylim(0, 1)
        ax.set_xlabel("Market price of Yes")
    axes[0].set_ylabel("How often Yes happened")
    legend = axes[0].legend(loc="upper left", fontsize=8.5, frameon=False)
    for text in legend.get_texts():
        text.set_color(t["text"])
    _save(fig, path)


def chart_category_slopes(table, path, theme):
    t = THEMES[theme]
    fig, ax = _figure(theme, figsize=(8, 0.55 * len(table) + 1.4))
    _style(ax, theme)
    ys = list(range(len(table)))[::-1]
    label_box = {"facecolor": t["surface"], "edgecolor": "none", "pad": 1.5}
    for y, row in zip(ys, table.itertuples(index=False), strict=True):
        label = f"{row.category}  ({row.markets:,} markets)"
        ax.text(-0.02, y, label, transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=9, color=t["text"])
        if math.isnan(row.b):
            ax.text(1.0, y, "too few markets", ha="center", va="center", fontsize=8, color=t["muted"],
                    bbox=label_box)
            continue
        ax.plot([row.b_low, row.b_high], [y, y], color=t["series"][0], linewidth=2,
                solid_capstyle="round")
        ax.plot(row.b, y, "o", color=t["series"][0], markersize=7)
        ax.text(row.b_high + 0.03, y, f"b = {row.b:.2f}", va="center", fontsize=8, color=t["muted"],
                bbox=label_box)
    ax.axvline(1.0, color=t["muted"], linestyle="--", linewidth=1)
    ax.text(1.0, len(table) - 0.35, "calibrated (b = 1)", ha="center", fontsize=8, color=t["muted"],
            bbox=label_box)
    ax.set_yticks([])
    ax.set_ylim(-0.7, len(table) - 0.1)
    ax.set_xlabel("Recalibration slope b  (above 1: prices too timid at the extremes)")
    _save(fig, path)


def chart_backtest(trades_by_timing, path, theme):
    t = THEMES[theme]
    fig, ax = _figure(theme, figsize=(8, 3.8))
    _style(ax, theme)
    ax.axhline(0, color=t["muted"], linewidth=1)
    for (timing, trades), color in zip(trades_by_timing.items(), t["series"], strict=True):
        if trades.empty:
            continue
        monthly = trades.groupby("month_start")["pnl"].sum().cumsum()
        dates = pd.to_datetime(monthly.index, unit="s")
        ax.plot(dates, monthly.values, color=color, linewidth=2, label=TIMING_LABELS[timing])
        ax.text(dates[-1], monthly.values[-1], f"  {monthly.values[-1]:+.1f}", va="center",
                fontsize=9, color=t["text"])
    ax.set_ylabel(r"Cumulative profit (\$ per \$1 contract)")
    legend = ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=8.5,
                       frameon=False)
    for text in legend.get_texts():
        text.set_color(t["text"])
    _save(fig, path)


def _picture(name, alt):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="figures/{name}-dark.png">'
            f'<img src="figures/{name}-light.png" alt="{alt}" width="100%"></picture>')


def _fmt(x, digits=3):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}"


def _sample_name(summary: dict) -> str:
    if summary["horizon"] == DECISION:
        return "open then"
    return "excl. early" if summary["exclude_early"] else "all"


def _backtest_summary(trades: pd.DataFrame, n_boot: int) -> dict:
    if trades.empty:
        return {"trades": 0}
    low, high = cluster_bootstrap(trades, "event_id", lambda d: d["pnl"].mean(),
                                  n_boot=max(n_boot, 200), seed=1)
    return {"trades": len(trades), "events": trades["event_id"].nunique(),
            "mean_pnl": trades["pnl"].mean(), "low": low, "high": high,
            "hit_rate": (trades["pnl"] > 0).mean(), "yes_share": (trades["side"] == "yes").mean(),
            "first": datetime.fromtimestamp(trades["month_start"].min(), UTC).strftime("%b %Y"),
            "last": datetime.fromtimestamp(trades["month_start"].max(), UTC).strftime("%b %Y")}


def build_report(study: pd.DataFrame, out_dir: Path, data_note: str, n_boot: int = 1000) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    study = study.copy()
    study["resolved_early"] = study["resolved_early"].astype(bool)

    summaries = [summarise(study, h, exclude_early=ex, n_boot=n_boot)
                 for h in HORIZON_NAMES for ex in (False, True)]
    summaries.append(summarise(study, DECISION, exclude_early=False, n_boot=n_boot))
    categories = by_category(study, horizon=DECISION)
    trades = {timing: walk_forward(study, timing=timing, **BACKTEST) for timing in TIMING_LABELS}
    bt = {timing: _backtest_summary(t, n_boot) for timing, t in trades.items()}

    for theme in THEMES:
        chart_reliability(study, out_dir / "figures" / f"reliability-{theme}.png", theme)
        chart_category_slopes(categories, out_dir / "figures" / f"category_slopes-{theme}.png", theme)
        chart_backtest(trades, out_dir / "figures" / f"backtest-{theme}.png", theme)

    lines = [
        "# Calibration atlas: results",
        "",
        (f"Generated {datetime.now(UTC):%d %B %Y} from {data_note}. Every number below is "
        "recomputed by `calatlas report`."),
        "",
        "## Sample",
        "",
        (f"- **{len(study):,} markets** in **{study['event_id'].nunique():,} events**: resolved "
        f"Yes/No Polymarket markets that settled cleanly at 1 or 0, with at least "
        f"${MIN_VOLUME:,} traded. These rules were fixed before looking at any results."),
        (f"- **{study['resolved_early'].mean():.0%} resolved early** (closed over a day before "
        "their scheduled end, usually because the event had already happened). Their late "
        "prices already know the answer, so every result is shown with and without them."),
        ("- Price coverage: " + ", ".join(
            f"{study[f'price_{h}'].notna().mean():.0%} of markets have a price {name}"
            for h, name in HORIZON_NAMES.items()) + ". A market is left out of a horizon when it "
         "is younger than the horizon or has no price point fresh enough."),
        (f"- Yes happened in **{study['outcome'].mean():.1%}** of markets: multi-outcome events "
        "contribute many long shots."),
        "",
        "## Calibration by horizon",
        "",
        _picture("reliability", "Reliability diagrams at 30, 7 and 1 day before close"),
        "",
        "| Horizon | Sample | Markets | Events | Brier (95% CI) | Reliability | Resolution | a | b (± s.e.) |",
        "|---|---|--:|--:|---|--:|--:|--:|---|",
    ]
    for s in summaries:
        ci = f" ({_fmt(s.get('brier_low'))}–{_fmt(s.get('brier_high'))})" if "brier_low" in s else ""
        lines.append(
            f"| {TABLE_NAMES[s['horizon']]} | {_sample_name(s)} | "
            f"{s['markets']:,} | {s['events']:,} | {_fmt(s['brier'])}{ci} | {_fmt(s['reliability'], 4)} | "
            f"{_fmt(s['resolution'], 4)} | {_fmt(s['a'], 2)} | {_fmt(s['b'], 2)} ± {_fmt(s['se_b'], 2)} |")
    lines += [
        "",
        ("**Reading the table.** Brier is the mean squared error of the price as a forecast (lower "
        "is better). Reliability measures miscalibration (lower is better); resolution measures how "
        "well prices separate what happened from what didn't (higher is better). The recalibration "
        "fit is logit(P(Yes)) = a + b·logit(price): **b above 1 means prices are too timid at the "
        "extremes** (favourites win more often, and long shots less often, than their prices say). "
        "Standard errors and intervals are clustered by event. The last row measures every market "
        "at a time known in advance (7 days before its scheduled end, if it was still open then); "
        "\"before close\" rows rely on the actual close, which an early resolution only reveals "
        "afterwards."),
        "",
        "## By category",
        "",
        ("Recalibration slope 7 days before the scheduled end (markets still open then), the "
         "backtest's decision time, with 95% intervals clustered by event."),
        "",
        _picture("category_slopes", "Recalibration slope by category"),
        "",
        "| Category | Markets | Events | b | 95% interval |",
        "|---|--:|--:|--:|---|",
    ]
    for row in categories.itertuples(index=False):
        interval = "too few markets" if math.isnan(row.b) else f"{row.b_low:.2f} to {row.b_high:.2f}"
        lines.append(f"| {row.category} | {row.markets:,} | {row.events:,} | {_fmt(row.b, 2)} | {interval} |")
    lines += ["", "## Walk forward backtest", ""]
    honest = bt["scheduled"]
    if honest["trades"]:
        lines += [
            (f"Each month the recalibration is refitted using only markets that had **already "
            f"resolved**, then used to trade markets 7 days before their **scheduled** end, buying "
            f"whichever side the recalibrated probability favours by more than the cost. The "
            f"scheduled end is known in advance; the actual close is not, because many markets "
            f"close early. The second line times the same strategy from the actual close, which "
            f"quietly peeks at early resolutions; it is shown only to measure how much that "
            f"flatters the result. Cost assumed: {BACKTEST['cost']:.2f} per contract (half spread "
            f"plus fees), on a $1 payout contract."),
            "",
            _picture("backtest", "Cumulative profit of the walk forward strategy, honest and leaky timing"),
            "",
            "| Timing | Trades | Events | Months | Mean profit per contract (95% CI) | Winning trades | Bought Yes |",
            "|---|--:|--:|---|---|--:|--:|",
        ]
        for timing, b in bt.items():
            if b["trades"]:
                lines.append(
                    f"| {TIMING_LABELS[timing]} | {b['trades']:,} | {b['events']:,} | "
                    f"{b['first']} to {b['last']} | **{b['mean_pnl']:+.4f}** "
                    f"({b['low']:+.4f} to {b['high']:+.4f}) | {b['hit_rate']:.1%} | {b['yes_share']:.1%} |")
        lines += ["", "Intervals resample whole events."]
    else:
        lines.append("Not enough resolved markets to start the walk forward test.")
    lines += [
        "",
        "## Limits",
        "",
        ("- Prices are Polymarket's published price history, not executable bid/ask quotes; the "
        "backtest's flat cost is an assumption, and real fills on thin markets would be worse."),
        "- The sample is the highest-volume closed events, so it describes liquid markets, not all of them.",
        ("- Markets in one event are correlated; intervals are clustered by event, but categories are "
        "assigned from event tags, which are imperfect."),
        "- Research on read only public data. Nothing here is trading advice.",
        "",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return {"summaries": summaries, "categories": categories, "backtest": bt}
