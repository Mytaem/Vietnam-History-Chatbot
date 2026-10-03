"""Load configs/settings.yaml + .env → Settings (PLAN.md Mục 7)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs"


class Settings(dict):
    """Dict truy cập được dạng thuộc tính: settings.llm.chat_model."""

    def __getattr__(self, key: str) -> Any:
        try:
            value = self[key]
        except KeyError as e:
            raise AttributeError(key) from e
        return Settings(value) if isinstance(value, dict) else value


@lru_cache
def get_settings(path: str | Path = CONFIG_DIR / "settings.yaml") -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # Biến môi trường ghi đè file cấu hình
    data["llm"]["host"] = os.getenv("OLLAMA_HOST", data["llm"]["host"])
    data["neo4j"]["uri"] = os.getenv("NEO4J_URI", data["neo4j"]["uri"])
    data["neo4j"]["user"] = os.getenv("NEO4J_USER", data["neo4j"]["user"])
    data["llm"]["chat_model"] = os.getenv("CHAT_MODEL", data["llm"]["chat_model"])
    data["llm"]["extract_model"] = os.getenv("EXTRACT_MODEL", data["llm"]["extract_model"])
    data["neo4j"]["password"] = os.getenv("NEO4J_PASSWORD", "")
    data["project_root"] = str(PROJECT_ROOT)
    return Settings(data)
