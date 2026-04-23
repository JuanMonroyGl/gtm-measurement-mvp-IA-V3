"""Small JSON file cache for AI module calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class AICache:
    def __init__(self, cache_dir: str) -> None:
        self.root = Path(cache_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def build_key(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _path(self, namespace: str, key: str) -> Path:
        ns_dir = self.root / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        return ns_dir / f"{key}.json"

    def read(self, namespace: str, key: str) -> dict[str, Any] | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def write(self, namespace: str, key: str, payload: dict[str, Any]) -> None:
        path = self._path(namespace, key)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
