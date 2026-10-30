"""Tiny shared HTTP helper with retries."""
from __future__ import annotations

import time

import requests

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "vol-dashboard/0.1 (personal research project)"


def get_json(url: str, params: dict | None = None, retries: int = 2, timeout: int = 30):
    last = None
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:  # rate limited - back off
                time.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed: {last}")
