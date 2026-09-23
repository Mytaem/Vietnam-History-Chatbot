"""Cache đĩa cho kết quả LLM theo sha1(prompt_version + input) → resume được. (M4)"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        path = self.dir / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def set(self, key: str, value: Any) -> None:
        (self.dir / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
