import re
from pathlib import Path

import pandas as pd
import pytest

from calibration_atlas import dataset, markets, protocol
from calibration_atlas.analysis import by_category
from calibration_atlas.report import CATEGORY_RULES, DECISION

ROOT = Path(__file__).resolve().parents[1]


def recorded_fingerprint() -> str:
    text = (ROOT / "PROTOCOL.md").read_text()
    return re.search(r"Fingerprint: `([0-9a-f]{64})`", text).group(1)


def test_sampling_rules_match_the_frozen_protocol():
    """If this fails, a rule changed after the freeze. Undo it, or log a dated amendment
    in PROTOCOL.md and record the new fingerprint there (`calatlas fingerprint`)."""
    assert protocol.fingerprint() == recorded_fingerprint()


def test_editing_a_rule_function_changes_the_fingerprint(monkeypatch):
    before = protocol.fingerprint()
    monkeypatch.setattr(markets, "outcome_from_prices", lambda prices, outcomes: 1)
    assert protocol.fingerprint() != before


@pytest.mark.parametrize("module, name, value", [
    (dataset, "MIN_VOLUME", 5_000),
    (markets, "EARLY_MARGIN", markets.EARLY_MARGIN * 2),
    (protocol, "MIN_EVENTS", 30),
])
def test_changing_any_rule_changes_the_fingerprint(monkeypatch, module, name, value):
    before = protocol.fingerprint()
    monkeypatch.setattr(module, name, value)
    assert protocol.fingerprint() != before


def test_holdout_cutoff_is_after_every_market_in_the_study():
    study = pd.read_csv(ROOT / "data" / "study.csv")
    assert study["closed_ts"].max() < protocol.CUTOFF_TS


def test_the_claim_under_test_is_quoted_from_the_committed_data():
    study = pd.read_csv(ROOT / "data" / "study.csv", dtype={"market_id": str, "event_id": str})
    cats = by_category(study, horizon=DECISION, **CATEGORY_RULES).set_index("category")
    macro, o = cats.loc[protocol.HYPOTHESIS["category"]], protocol.ORIGINAL
    assert (macro["markets"], macro["events"]) == (o["markets"], o["events"])
    assert macro["b"] == pytest.approx(o["b"], abs=0.005)
    assert (macro["b_low"], macro["b_high"]) == pytest.approx((o["low"], o["high"]), abs=0.005)


def test_power_figures_quoted_in_the_protocol_are_current():
    from calibration_atlas.holdout import power

    text = (ROOT / "PROTOCOL.md").read_text()
    for b in (protocol.ORIGINAL["b"], protocol.ORIGINAL["pooled"]):
        assert f"about {power(b):.0%} if the true slope is {b:.2f}" in text
