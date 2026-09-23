"""LLM phân tích câu hỏi → QueryPlan. (M6)"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

Intent = Literal["factoid", "multihop", "temporal", "relational", "comparison", "overview"]


class QueryPlan(BaseModel):
    intent: Intent
    entities: list[str] = []
    rel_hints: list[str] = []
    rewritten: str
    time_range: Optional[tuple[int, int]] = None
    periods: list[str] = []


def analyze(question: str, history: list[dict]) -> QueryPlan:
    raise NotImplementedError
