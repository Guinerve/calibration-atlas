import json
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
import pandas as pd
import pytest

from calibration_atlas import protocol as P
from calibration_atlas.fetch import Fetcher
from calibration_atlas.holdout import (
    collect_holdout,
    evaluate,
    export_status,
    holdout_markets,
    power,
    verdict,
    write_holdout_report,
)
from calibration_atlas.recalibration import sigmoid

DAY = 86_400
AFTER = P.CUTOFF_TS + 30 * DAY
AS_OF = P.DEADLINE - timedelta(days=1)


def iso(ts):
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M:%S+00")


def market(id_, closed, end=None, token=None, prices='["1", "0"]'):
    return {"id": id_, "question": f"Q{id_}", "outcomes": '["Yes", "No"]', "outcomePrices": prices,
            "volumeNum": 50_000, "clobTokenIds": f'["{token or "tok-" + id_}", "no"]',
            "closedTime": iso(closed), "endDate": iso(end or closed)}


def event(id_, closed, markets, tags=("Economy",), volume=10_000_000):
    return {"id": id_, "closedTime": iso(closed), "volume": volume,
            "tags": [{"label": t} for t in tags], "markets": markets}


def test_only_macro_markets_closed_after_the_cutoff_and_open_at_decision_time_are_kept():
    kept = holdout_markets(event("e", AFTER, [
        market("new", AFTER),
        market("old", P.CUTOFF_TS - DAY),  # closed before the cutoff: seen data
        market("early", AFTER - 20 * DAY, end=AFTER),  # closed before its decision time
    ]))
    assert [m["market_id"] for m in kept] == ["new"]
    assert kept[0]["event_volume"] == 10_000_000 and kept[0]["event_closed_ts"] == AFTER
    assert holdout_markets(event("s", AFTER, [market("x", AFTER)], tags=("Sports", "Economy"))) == []
    assert holdout_markets(event("o", P.CUTOFF_TS, [market("y", AFTER)])) == []


class StubFetcher:
    def __init__(self, events, histories):
        self.events, self.histories = events, histories

    def closed_since(self, since_ts, min_volume):
        assert since_ts == P.CUTOFF_TS and min_volume == P.SECONDARY_MIN_EVENT_VOLUME
        return iter(self.events)

    def history(self, token_id, closed_ts):
        if token_id not in self.histories:
            raise RuntimeError("HTTP 500")
        return self.histories[token_id]


def test_collect_reads_the_decision_price_drops_repeats_and_records_failures(tmp_path):
    e = event("e1", AFTER, [market("a", AFTER), market("b", AFTER)])
    histories = {"tok-a": [{"t": AFTER - 7 * DAY - 600, "p": 0.8}]}
    meta = collect_holdout(StubFetcher([e, e], histories), tmp_path, workers=2, now=AS_OF)
    rows = pd.read_csv(tmp_path / "holdout.csv", dtype={"market_id": str})
    assert list(rows["market_id"]) == ["a"] and rows["price_sched_7d"].iloc[0] == 0.8
    assert list(pd.read_csv(tmp_path / "holdout-errors.csv", dtype=str)["market_id"]) == ["b"]
    assert meta == {"collected_at": AS_OF.isoformat(timespec="seconds"), "events_listed": 1,
                    "markets": 2, "rows": 1, "errors": 1}


def simulated_holdout(n_events, b=1.0, per_event=8, seed=0, start=AFTER, volume=10_000_000):
    rng = np.random.default_rng(seed)
    n = n_events * per_event
    price = sigmoid(rng.normal(0, 1.5, n))
    outcome = (rng.random(n) < sigmoid(b * np.log(price / (1 - price)))).astype(int)
    event = np.arange(n) // per_event
    return pd.DataFrame({
        "market_id": [f"h{seed}-{i}" for i in range(n)], "event_id": [f"e{seed}-{e}" for e in event],
        "category": "macro", "outcome": outcome, "price_sched_7d": price,
        "closed_ts": start + event * DAY, "event_closed_ts": start + event * DAY,
        "event_volume": volume})


def test_the_slope_stays_hidden_until_the_primary_sample_is_complete():
    result = evaluate(simulated_holdout(P.MIN_EVENTS - 1), set(), as_of=AS_OF)
    assert result["status"] == "blinded" and "results" not in result
    assert result["progress"]["primary"]["events"] == P.MIN_EVENTS - 1


def test_the_test_reads_only_the_first_events_to_close_so_later_data_cannot_move_it():
    first = simulated_holdout(P.MIN_EVENTS, b=1.0)
    later = simulated_holdout(60, b=4.0, seed=1, start=AFTER + 100 * DAY)
    read = evaluate(first, set(), as_of=AS_OF)
    read_later = evaluate(pd.concat([first, later]), set(), as_of=AS_OF)
    assert read["status"] == "read"
    assert read["results"]["primary"]["events"] == P.MIN_EVENTS
    assert read_later["results"]["primary"]["b"] == pytest.approx(read["results"]["primary"]["b"])


def test_small_events_count_only_toward_the_secondary_population():
    big = simulated_holdout(P.MIN_EVENTS)
    small = simulated_holdout(30, seed=2, volume=50_000)
    result = evaluate(pd.concat([big, small]), set(), as_of=AS_OF)
    assert result["results"]["primary"]["events"] == P.MIN_EVENTS
    assert result["results"]["secondary"]["events"] == P.MIN_EVENTS + 30


def test_markets_already_in_the_study_are_never_counted():
    holdout = simulated_holdout(P.MIN_EVENTS)
    result = evaluate(holdout, set(holdout["market_id"]), as_of=AS_OF)
    assert result["progress"]["primary"]["markets"] == 0


def test_after_the_deadline_the_test_is_read_on_what_there_is():
    result = evaluate(simulated_holdout(40), set(), as_of=P.DEADLINE + timedelta(days=1))
    assert result["status"] == "read, underpowered"
    assert result["results"]["primary"]["events"] == 40


def test_a_true_effect_is_supported_and_a_calibrated_market_is_not():
    strong = evaluate(simulated_holdout(P.MIN_EVENTS, b=2.5, per_event=20), set(), as_of=AS_OF)
    calibrated = evaluate(simulated_holdout(P.MIN_EVENTS, b=1.0, per_event=20), set(), as_of=AS_OF)
    assert strong["results"]["primary"]["verdict"] == "supported"
    assert calibrated["results"]["primary"]["verdict"] == "not supported"


def test_events_count_only_once_settled_and_never_after_the_deadline():
    recent = simulated_holdout(P.MIN_EVENTS, start=int(AS_OF.timestamp()) - 3 * DAY)
    assert evaluate(recent, set(), as_of=AS_OF)["progress"]["primary"]["events"] == 0
    late = simulated_holdout(P.MIN_EVENTS, start=int(P.DEADLINE.timestamp()) + DAY)
    result = evaluate(late, set(), as_of=P.DEADLINE + timedelta(days=400))
    assert result["status"] == "read, underpowered"
    assert result["results"]["primary"]["events"] == 0


def test_verdict_rules():
    assert verdict({"b": 1.5, "one_sided_low": 1.05, "high": 2.0}) == "supported"
    assert verdict({"b": 0.6, "one_sided_low": 0.4, "high": 0.9}) == "reversed"
    assert verdict({"b": 1.2, "one_sided_low": 0.9, "high": 1.6}) == "not supported"
    assert verdict({"b": None}) == "no stable fit"


def test_power_rises_with_the_true_effect():
    assert power(1.0) == pytest.approx(P.ALPHA, abs=1e-9)
    assert power(1.29) < 0.5 < power(1.66)


def test_blinded_outputs_contain_counts_but_no_slope(tmp_path):
    result = evaluate(simulated_holdout(10), set(), as_of=AS_OF)
    write_holdout_report(result, tmp_path / "HOLDOUT.md")
    export_status(result, tmp_path / "holdout.json")
    page = (tmp_path / "HOLDOUT.md").read_text()
    assert "**blinded**" in page and "## Result" not in page and P.fingerprint() in page
    status = json.loads((tmp_path / "holdout.json").read_text())
    assert status["status"] == "blinded" and "results" not in status
    assert status["progress"]["primary"]["events"] == 10


def test_read_outputs_show_the_verdict(tmp_path):
    result = evaluate(simulated_holdout(P.MIN_EVENTS), set(), as_of=AS_OF)
    write_holdout_report(result, tmp_path / "HOLDOUT.md")
    assert "## Result" in (tmp_path / "HOLDOUT.md").read_text()


def test_closed_since_pages_newest_first_stops_at_the_cutoff_and_never_uses_the_cache(tmp_path):
    calls = []

    def handler(request):
        q = request.url.params
        calls.append(int(q["offset"]))
        assert q["order"] == "closedTime" and q["ascending"] == "false" and q["volume_min"] == "10000"
        start = AFTER - int(q["offset"]) * 3_600
        return httpx.Response(200, json=[{"id": str(int(q["offset"]) + i),
                                          "closedTime": iso(start - i * 3_600)} for i in range(100)])

    fetcher = Fetcher(cache_dir=tmp_path, client=httpx.Client(transport=httpx.MockTransport(handler)),
                      pause=0)
    events = list(fetcher.closed_since(AFTER - 150 * 3_600, min_volume=10_000))
    assert len(events) == 150 and calls == [0, 100]
    list(fetcher.closed_since(AFTER - 150 * 3_600, min_volume=10_000))
    assert calls == [0, 100, 0, 100]
