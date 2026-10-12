import json

import httpx
import pytest

from calibration_atlas.fetch import Fetcher

CLOSED = 1_730_906_261  # 2024-11-06T15:17:41Z


def make_fetcher(tmp_path, handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(cache_dir=tmp_path, client=client, pause=0)


def test_history_merges_the_full_lifetime_with_recent_hourly_points(tmp_path):
    def handler(request):
        q = request.url.params
        if q.get("interval") == "max":
            assert q["fidelity"] == "720"
            return httpx.Response(200, json={"history": [{"t": 100, "p": 0.4}, {"t": 500, "p": 0.6}]})
        assert int(q["endTs"]) - int(q["startTs"]) <= 15 * 86_400
        assert q["fidelity"] == "60"
        return httpx.Response(200, json={"history": [{"t": 500, "p": 0.6}, {"t": 900, "p": 0.7}]})

    history = make_fetcher(tmp_path, handler).history("token-1", closed_ts=CLOSED)
    assert history == [{"t": 100, "p": 0.4}, {"t": 500, "p": 0.6}, {"t": 900, "p": 0.7}]


def test_responses_are_cached_on_disk(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"history": [{"t": 1, "p": 0.5}]})

    make_fetcher(tmp_path, handler).history("token-1", closed_ts=CLOSED)
    first = len(calls)
    make_fetcher(tmp_path, handler).history("token-1", closed_ts=CLOSED)
    assert len(calls) == first == 2


def test_closed_events_are_paged_until_a_short_page(tmp_path):
    def handler(request):
        offset = int(request.url.params["offset"])
        assert request.url.params["closed"] == "true"
        size = 37 if offset == 200 else 100
        return httpx.Response(200, json=[{"id": str(offset + i)} for i in range(size)])

    events = list(make_fetcher(tmp_path, handler).closed_events(max_events=1_000))
    assert len(events) == 237
    assert events[-1]["id"] == "236"


def test_closed_events_stop_at_the_limit(tmp_path):
    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=[{"id": str(offset + i)} for i in range(100)])

    assert len(list(make_fetcher(tmp_path, handler).closed_events(max_events=150))) == 150


def test_transient_errors_are_retried(tmp_path):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"history": []})

    fetcher = make_fetcher(tmp_path, handler)
    assert fetcher.get_json("https://clob.polymarket.com/prices-history", {"market": "x"}) == {"history": []}
    assert len(attempts) == 3


def test_a_permanent_error_is_raised_not_hidden(tmp_path):
    fetcher = make_fetcher(tmp_path, lambda request: httpx.Response(400, json={"error": "bad"}))
    with pytest.raises(httpx.HTTPStatusError):
        fetcher.get_json("https://clob.polymarket.com/prices-history", {"market": "x"})


def test_cache_files_record_when_they_were_downloaded(tmp_path):
    make_fetcher(tmp_path, lambda r: httpx.Response(200, json={"ok": 1})).get_json(
        "https://gamma-api.polymarket.com/events", {"offset": 0})
    (cached,) = list(tmp_path.rglob("*.json"))
    record = json.loads(cached.read_text())
    assert record["url"].startswith("https://gamma-api.polymarket.com/events")
    assert "downloaded_at" in record and record["body"] == {"ok": 1}
