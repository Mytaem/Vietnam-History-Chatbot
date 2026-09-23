"""RRF có trọng số theo intent, boost chunk là evidence của cạnh, rerank (tùy chọn). (M6)"""
from __future__ import annotations


def rrf(ranked_lists: list[list[dict]], weights: list[float], k: int = 60) -> list[dict]:
    raise NotImplementedError


def boost_evidence(items: list[dict], evidence_ids: set[str], factor: float = 1.3) -> list[dict]:
    raise NotImplementedError


def rerank(question: str, items: list[dict]) -> list[dict]:
    raise NotImplementedError
