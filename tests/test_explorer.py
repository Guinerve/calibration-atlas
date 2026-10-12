import json
import math

import pandas as pd

from calibration_atlas.explorer import export_markets


def study():
    return pd.DataFrame({
        "market_id": ["m1", "m2", "m3"], "event_id": ["e1", "e1", "e2"],
        "category": ["sports", "sports", "macro"], "outcome": [1, 0, 0],
        "volume": [12_345.6, 50_000.0, 2_000_000.0], "resolved_early": [False, True, False],
        "price_30d": [math.nan, 0.2, 0.01], "price_7d": [0.61234, 0.3, 0.02],
        "price_1d": [0.9, 0.1, 0.001], "price_sched_7d": [0.6, math.nan, 0.02],
    })


def test_export_is_compact_columns_with_nulls_for_missing_prices(tmp_path):
    path = tmp_path / "markets.json"
    export_markets(study(), path, data_note="test data")
    data = json.loads(path.read_text())
    assert data["note"] == "test data" and data["categories"] == ["macro", "sports"]
    assert data["category"] == [1, 1, 0] and data["event"] == [0, 0, 1]
    assert data["outcome"] == [1, 0, 0] and data["early"] == [0, 1, 0]
    assert data["volume"] == [12346, 50000, 2000000]
    assert data["price"]["30d"][0] is None and data["price"]["7d"][0] == 0.6123
    assert data["price"]["sched_7d"] == [0.6, None, 0.02]


def run_js_stats(price, outcome, cluster):
    import os
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    if shutil.which("node") is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI so the explorer parity check cannot be skipped")
        pytest.skip("node is not installed")
    script = Path(__file__).parent / "js" / "check_stats.mjs"
    payload = json.dumps({"price": list(map(float, price)), "outcome": list(map(int, outcome)),
                          "cluster": list(map(int, cluster))})
    out = subprocess.run(["node", str(script)], input=payload, capture_output=True, text=True,
                         check=True)
    return json.loads(out.stdout)


def test_browser_statistics_match_the_python_analysis():
    import numpy as np
    import pytest

    from calibration_atlas.metrics import brier_score, reliability_table
    from calibration_atlas.recalibration import fit_recalibration, simulate_markets

    sim = simulate_markets(a=0.2, b=1.3, n=3_000, seed=8, markets_per_event=3)
    sim.loc[:20, "price"] = 0.0005  # sub cent prices, as in the real data
    js = run_js_stats(sim["price"], sim["outcome"], sim["event"])
    fit = fit_recalibration(sim["price"], sim["outcome"], sim["event"])
    assert js["fit"]["a"] == pytest.approx(fit.a, abs=1e-6)
    assert js["fit"]["b"] == pytest.approx(fit.b, abs=1e-6)
    assert js["fit"]["seA"] == pytest.approx(fit.se_a, rel=1e-4)
    assert js["fit"]["seB"] == pytest.approx(fit.se_b, rel=1e-4)
    assert js["brier"] == pytest.approx(brier_score(sim["price"].to_numpy(), sim["outcome"].to_numpy()))
    table = reliability_table(sim["price"].to_numpy(), sim["outcome"].to_numpy(), bins=10)
    assert [b["count"] for b in js["bins"]] == table["count"].tolist()
    assert np.allclose([b["observed"] for b in js["bins"]], table["observed"])


def test_browser_fit_reports_failure_instead_of_a_huge_slope_when_outcomes_separate():
    import numpy as np

    price = np.linspace(0.05, 0.95, 60)
    outcome = (price > 0.5).astype(int)  # perfectly separated: no finite maximum likelihood
    js = run_js_stats(price, outcome, np.arange(60) // 3)
    assert js["fit"]["converged"] is False
