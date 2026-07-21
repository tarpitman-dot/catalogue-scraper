from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import requests

from sources.base import SourceError


@dataclass
class RateLimiter:
    min_interval: float = 1.0
    _last: float = field(default=0.0, init=False)

    def wait(self) -> None:
        now = time.monotonic()
        delay = self.min_interval - (now - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


class HttpClient:
    def __init__(self, source: str, user_agent: str, min_interval: float = 0.0, timeout: int = 30):
        self.source = source
        self.timeout = timeout
        self.limiter = RateLimiter(min(0.0, min_interval) if min_interval < 0 else min_interval)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        attempts = int(kwargs.pop("attempts", 3))
        retry_statuses = {429, 500, 502, 503, 504}
        for attempt in range(attempts):
            self.limiter.wait()
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                if attempt == attempts - 1:
                    raise SourceError(f"{self.source} request failed: {exc}") from exc
                time.sleep(2 ** attempt)
                continue
            if response.status_code in retry_statuses and attempt < attempts - 1:
                retry_after = response.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
                continue
            if 400 <= response.status_code < 500 and response.status_code != 429:
                raise SourceError(f"{self.source} request failed ({response.status_code}): {response.text[:200]}")
            if not response.ok:
                raise SourceError(f"{self.source} request failed ({response.status_code}): {response.text[:200]}")
            return response
        raise SourceError(f"{self.source} request failed after retries.")

    def get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", url, **kwargs).json()

    def post_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("POST", url, **kwargs).json()
