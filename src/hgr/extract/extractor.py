"""Chạy pass 1 (entity) → pass 2 (relation) → (pass 3 gleaning) cho mỗi chunk. (M4)"""
from __future__ import annotations


def extract_chunk(chunk: dict, period: dict) -> dict:
    """→ {chunk_id, entities[], triplets[], rejects[]} (có cache)."""
    raise NotImplementedError


def run(era: str | None = None, period: str | None = None, tier: str | None = None) -> None:
    """Tier A: mọi chunk; Tier B: max_chunks_b chunk đầu. 2 worker, resume theo cache."""
    raise NotImplementedError
