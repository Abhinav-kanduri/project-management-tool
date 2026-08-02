from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any


class SummaryCache:
    def __init__(self, *, enabled: bool, directory: Path, ttl_seconds: int) -> None:
        self._enabled = enabled
        self._directory = directory
        self._ttl_seconds = ttl_seconds

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._directory / f"{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self._enabled:
            return None
        path = self._path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if time.time() - float(payload.get("cached_at", 0)) > self._ttl_seconds:
            path.unlink(missing_ok=True)
            return None
        value = payload.get("value")
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self._enabled:
            return
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        payload = {"cached_at": time.time(), "value": value}
        try:
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

