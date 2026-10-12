import numpy as np
import pandas as pd

from calibration_atlas.recalibration import simulate_markets
from calibration_atlas.report import build_report

DAY = 86_400
START = 1_672_531_200


def simulated_study(n=6_000, seed=0):
    sim = simulate_markets(a=0.0, b=1.3, n=n, seed=seed, markets_per_event=3)
    rng = np.random.default_rng(seed)
    noise = lambda: np.clip(sim["price"] + rng.normal(0, 0.03, n), 0.01, 0.99)
    return pd.DataFrame({
        "market_id": [f"m{i}" for i in range(n)], "event_id": sim["event"].astype(str),
        "question": "Q", "outcome": sim["outcome"],
        "price_30d": noise(), "price_7d": sim["price"], "price_1d": noise(),
        "category": rng.choice(["sports", "politics", "macro"], n),
        "resolved_early": rng.random(n) < 0.3,
        "closed_ts": START + rng.uniform(0, 20 * 30 * DAY, n).astype(int),
    }).assign(end_ts=lambda d: d["closed_ts"], price_sched_7d=lambda d: d["price_7d"])


def test_report_writes_markdown_and_both_chart_themes(tmp_path):
    results = build_report(simulated_study(), out_dir=tmp_path, data_note="simulated test data",
                           n_boot=50)
    report = (tmp_path / "REPORT.md").read_text()
    for heading in ["## Sample", "## Calibration by horizon", "## By category",
                    "## Walk forward backtest", "## Limits"]:
        assert heading in report
    assert "simulated test data" in report
    assert "Timed from the actual close" in report  # the leaky comparison is shown
    assert "| 7 days before scheduled end | open then |" in report
    assert set(results["backtest"]) == {"scheduled", "close"}
    for chart in ["reliability", "category_slopes", "backtest"]:
        for theme in ["light", "dark"]:
            assert (tmp_path / "figures" / f"{chart}-{theme}.png").stat().st_size > 10_000
    assert results["summaries"][0]["markets"] > 0
