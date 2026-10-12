import pandas as pd

from calibration_atlas.collect import collect

DAY = 86_400
CLOSE = 1_735_689_600  # 2025-01-01T00:00:00Z


def market(id_, token, prices='["1", "0"]'):
    return {"id": id_, "question": f"Q{id_}", "outcomes": '["Yes", "No"]', "outcomePrices": prices,
            "volumeNum": 50_000, "clobTokenIds": f'["{token}", "no"]',
            "closedTime": "2025-01-01 00:00:00+00", "endDate": "2025-01-01T00:00:00Z"}


class StubFetcher:
    def __init__(self, events, histories, broken=()):
        self.events, self.histories, self.broken = events, histories, set(broken)

    def closed_events(self, max_events):
        return iter(self.events[:max_events])

    def history(self, token_id, closed_ts):
        if token_id in self.broken:
            raise RuntimeError("HTTP 500")
        return self.histories[token_id]


EVENTS = [{"id": "e1", "tags": [{"label": "Sports"}],
           "markets": [market("a", "tok-a"), market("b", "tok-b", '["0", "1"]'), market("c", "tok-c")]}]
HISTORIES = {
    "tok-a": [{"t": CLOSE - 8 * DAY, "p": 0.6}, {"t": CLOSE - DAY - 600, "p": 0.9}],
    "tok-b": [{"t": CLOSE - 8 * DAY, "p": 0.3}],
}


def test_collect_writes_one_row_per_market_with_horizon_prices(tmp_path):
    summary = collect(StubFetcher(EVENTS, HISTORIES, broken={"tok-c"}), max_events=10,
                      out_dir=tmp_path, workers=2)
    study = pd.read_csv(tmp_path / "study.csv").set_index("market_id")
    assert list(study.index) == ["a", "b"]
    assert study.loc["a", "price_7d"] == 0.6 and study.loc["a", "price_1d"] == 0.9
    assert study.loc["a", "price_sched_7d"] == 0.6  # scheduled end equals the close here
    assert study.loc["b", "outcome"] == 0 and study.loc["b", "category"] == "sports"
    assert summary == {"events": 1, "markets": 3, "rows": 2, "errors": 1}


def test_failed_markets_are_recorded_not_silently_dropped(tmp_path):
    collect(StubFetcher(EVENTS, HISTORIES, broken={"tok-c"}), max_events=10, out_dir=tmp_path, workers=1)
    errors = pd.read_csv(tmp_path / "errors.csv")
    assert list(errors["market_id"]) == ["c"]
    assert "HTTP 500" in errors["error"].iloc[0]


def test_collection_date_is_recorded_rather_than_read_from_file_times(tmp_path):
    import json
    from datetime import UTC, datetime

    collect(StubFetcher(EVENTS, HISTORIES), max_events=10, out_dir=tmp_path, workers=1)
    meta = json.loads((tmp_path / "collection.json").read_text())
    assert meta["collected"] == datetime.now(UTC).date().isoformat()
    assert meta["events"] == 1 and meta["markets"] == 3
