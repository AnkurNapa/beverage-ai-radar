from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
from typing import Callable


def _default_transport(url: str) -> str:
    import httpx

    return httpx.get(url, timeout=20, follow_redirects=True).text


class CachedFetcher:
    def __init__(
        self,
        cache_dir: Path,
        min_interval_s: float = 1.0,
        transport: Callable[[str], str] | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.transport = transport or _default_transport
        self._last_fetch = 0.0

    def _path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def fetch(self, url: str, ttl_hours: int = 24) -> str:
        p = self._path(url)
        if p.exists():
            entry = json.loads(p.read_text())
            age_h = (time.time() - entry["fetched_at"]) / 3600
            if age_h < ttl_hours:
                return entry["body"]
        gap = self.min_interval_s - (time.time() - self._last_fetch)
        if gap > 0:
            time.sleep(gap)
        body = self.transport(url)
        self._last_fetch = time.time()
        p.write_text(json.dumps({"fetched_at": time.time(), "body": body}))
        return body
