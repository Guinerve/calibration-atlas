import json

from test_holdout import AS_OF, simulated_holdout
from test_report import simulated_study

from calibration_atlas.cli import main


def test_report_command_rebuilds_the_report_explorer_data_and_holdout_page(tmp_path):
    data, out, site = tmp_path / "data", tmp_path / "reports", tmp_path / "docs"
    data.mkdir()
    study = simulated_study(n=3_000).assign(volume=50_000.0)
    study.to_csv(data / "study.csv", index=False)
    (data / "collection.json").write_text(json.dumps({"collected": "2026-10-12"}))
    simulated_holdout(10).to_csv(data / "holdout.csv", index=False)
    (data / "holdout.json").write_text(json.dumps({"collected_at": AS_OF.isoformat()}))

    assert main(["--data", str(data), "report", "--out", str(out), "--site", str(site),
                 "--n-boot", "0"]) == 0

    assert "collected 12 October 2026" in (out / "REPORT.md").read_text()
    markets = json.loads((site / "data" / "markets.json").read_text())
    assert len(markets["outcome"]) == 3_000
    status = json.loads((site / "data" / "holdout.json").read_text())
    assert status["status"] == "blinded" and status["progress"]["primary"]["events"] == 10
    assert "**blinded**" in (out / "HOLDOUT.md").read_text()
