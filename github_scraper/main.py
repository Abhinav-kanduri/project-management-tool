from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.config import Settings


class SummaryCache:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._settings.cache_directory / f"{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self._settings.cache_enabled:
            return None
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        created_at = float(payload.get("_cached_at_epoch", 0))
        if time.time() - created_at > self._settings.cache_ttl_seconds:
            path.unlink(missing_ok=True)
            return None
        value = payload.get("value")
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self._settings.cache_enabled:
            return
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        payload = {"_cached_at_epoch": time.time(), "value": value}
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(path)
