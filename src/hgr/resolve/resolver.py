"""Hợp nhất thực thể: link→QID → alias dict → fuzzy (blocking type + period) → local id. (M5)"""
from __future__ import annotations


class EntityResolver:
    def __init__(self, fuzzy_threshold: int = 92, event_year_tolerance: int = 1):
        self.fuzzy_threshold = fuzzy_threshold
        self.event_year_tolerance = event_year_tolerance

    def add_aliases(self, canonical_id: str, names: list[str]) -> None:
        raise NotImplementedError

    def resolve(self, entity: dict, chunk_links: list[dict], period_id: str) -> str:
        """→ canonical id (qid:Qxxx | local:<slug>)."""
        raise NotImplementedError


def run() -> None:
    """extractions + structured → data/resolved/entities.jsonl, relations.jsonl."""
    raise NotImplementedError
