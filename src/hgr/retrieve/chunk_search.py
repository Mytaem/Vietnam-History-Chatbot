"""Vector + fulltext trên Chunk, lọc năm/period, gộp RRF. (M6)"""
from __future__ import annotations


def search(query: str, k: int = 20, years: tuple[int, int] | None = None,
           periods: list[str] | None = None) -> list[dict]:
    raise NotImplementedError
