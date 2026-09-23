"""retrieve(question, history, period_filter) → RetrievalResult (PLAN.md 6.3). (M6)"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    plan: object | None = None
    top_chunks: list[dict] = field(default_factory=list)
    triplets: list[dict] = field(default_factory=list)
    paths: list = field(default_factory=list)
    subgraph: dict = field(default_factory=dict)
    out_of_scope: bool = False


def retrieve(question: str, history: list[dict] | None = None,
             period_filter: tuple[int, int] | None = None, mode: str = "graphrag") -> RetrievalResult:
    raise NotImplementedError
