"""Download Polymarket's public, read-only market data, with an on-disk cache.

Every response is stored with its URL and download time, so a study can be
re-run exactly from the cache and its data provenance stated.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .markets import parse_time

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
USER_AGENT = "calibration-atlas (research; read-only)"

# The price-history API serves a market's whole life at 12-hour resolution, and
# hourly points only in windows of up to 15 days, so each market takes two requests.
FULL_FIDELITY_MINUTES = 720
RECENT_FIDELITY_MINUTES = 60
RECENT_WINDOW_SECONDS = 14 * 86_400

RETRY_STATUSES = {429, 500, 502, 503, 504}


class Fetcher:
    def __init__(self, cache_dir: Path, client: httpx.Client | None = None,
                 pause: float = 0.25, retries: int = 4):
        self.cache_dir = Path(cache_dir)
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})
        self.pause = pause
        self.retries = retries

    def _cache_path(self, url: str, params: dict) -> Path:
        key = url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        host = httpx.URL(url).host
        return self.cache_dir / host / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"

    def get_json(self, url: str, params: dict, cache: bool = True):
        """``cache=False`` always downloads (and still records the response), for listings
        that change over time."""
        path = self._cache_path(url, params)
        if cache and path.exists():
            return json.loads(path.read_text())["body"]
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(url, params=params)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
            else:
                if response.status_code not in RETRY_STATUSES or attempt == self.retries:
                    response.raise_for_status()
                    break
            time.sleep(self.pause * 2 ** attempt)
        body = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "url": str(response.request.url),
            "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "body": body,
        }))
        time.sleep(self.pause)
        return body

    def closed_events(self, max_events: int, page_size: int = 100) -> Iterator[dict]:
        """Closed events with their markets and tags, highest volume first."""
        offset = 0
        while offset < max_events:
            page = self.get_json(f"{GAMMA}/events", {
                "closed": "true", "limit": page_size, "offset": offset,
                "order": "volume", "ascending": "false"})
            yield from page[: max_events - offset]
            if len(page) < page_size:
                return
            offset += page_size

    def closed_since(self, since_ts: int, min_volume: float, page_size: int = 100) -> Iterator[dict]:
        """Events that closed after ``since_ts`` (unix seconds) with at least ``min_volume``
        traded, newest first. The listing grows as markets close, so it is never read from
        the cache. New closes push older events down a page, which can repeat an event but
        never skip one; callers drop repeats by id."""
        offset = 0
        while True:
            page = self.get_json(f"{GAMMA}/events", {
                "closed": "true", "limit": page_size, "offset": offset, "order": "closedTime",
                "ascending": "false", "volume_min": min_volume}, cache=False)
            for event in page:
                closed = parse_time(event.get("closedTime"))
                if closed is None:
                    continue
                if closed.timestamp() <= since_ts:
                    return
                yield event
            if len(page) < page_size:
                return
            offset += page_size

    def history(self, token_id: str, closed_ts: int) -> list[dict]:
        """Price points for a token: the whole life at 12-hour resolution, plus hourly
        points for the two weeks before it closed. Sorted by time, without duplicates."""
        full = self.get_json(f"{CLOB}/prices-history", {
            "market": token_id, "interval": "max", "fidelity": FULL_FIDELITY_MINUTES})
        recent = self.get_json(f"{CLOB}/prices-history", {
            "market": token_id, "startTs": closed_ts - RECENT_WINDOW_SECONDS,
            "endTs": closed_ts, "fidelity": RECENT_FIDELITY_MINUTES})
        merged = {p["t"]: p for p in full.get("history", []) + recent.get("history", [])}
        return [merged[t] for t in sorted(merged)]
