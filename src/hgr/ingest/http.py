"""HTTP dùng chung cho MediaWiki/Wikidata: thử lại khi máy chủ bận + cache phản hồi ra đĩa để chạy lại/tiếp tục nhanh."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class Retryable(Exception):
    pass


class ApiClient:
    def __init__(self, api: str, user_agent: str, cache_dir: str | Path | None = None,
                 ttl_days: float = 7, timeout: float = 60.0):
        self.api = api
        self._http = httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout)
        self._cache = Path(cache_dir) if cache_dir else None
        self._ttl = ttl_days * 86400
        if self._cache:
            self._cache.mkdir(parents=True, exist_ok=True)

    def get(self, params: dict) -> dict:
        path = self._cache_path(params)
        if path and path.exists() and time.time() - path.stat().st_mtime < self._ttl:
            return json.loads(gzip.decompress(path.read_bytes()))
        data = self._fetch(params)
        if path:
            path.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8")))
        return data

    def _cache_path(self, params: dict) -> Path | None:
        if not self._cache:
            return None
        key = hashlib.sha1((self.api + json.dumps(params, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
        return self._cache / f"{key}.json.gz"

    # maxlag/429/5xx là lỗi tạm thời theo thiết kế của Wikimedia: chờ rồi thử lại, không bỏ cả lần build.
    @retry(
        retry=retry_if_exception_type((httpx.TransportError, Retryable)),
        stop=stop_after_attempt(12),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        reraise=True,
    )
    def _fetch(self, params: dict) -> dict:
        response = self._http.get(self.api, params=params)
        if response.status_code in (429, 500, 502, 503, 504):
            raise Retryable(f"HTTP {response.status_code}")
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            if data["error"].get("code") == "maxlag":
                raise Retryable("maxlag")
            raise RuntimeError(f"API lỗi ({self.api}): {data['error']}")
        return data
