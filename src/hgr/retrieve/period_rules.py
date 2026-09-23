"""Luật chạy TRƯỚC LLM: alias giai đoạn, "thế kỷ X", năm, kiểm tra > 1945 (PLAN.md 6.3 A0). (M6)"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuleResult:
    time_range: tuple[int, int] | None = None
    periods: list[str] = field(default_factory=list)
    out_of_scope: bool = False


def parse(question: str) -> RuleResult:
    raise NotImplementedError
