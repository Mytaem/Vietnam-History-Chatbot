"""Luật chạy TRƯỚC LLM: alias giai đoạn, "thế kỷ X", năm, kiểm tra > 1945 (PLAN.md 6.3 A0). (M6)"""
from __future__ import annotations

from dataclasses import dataclass, field

from hgr.config import get_settings
from hgr.periods import Era, Period, find_by_alias, periods_for_range


@dataclass
class RuleResult:
    time_range: tuple[int, int] | None = None
    periods: list[str] = field(default_factory=list)
    out_of_scope: bool = False


def parse(question: str) -> RuleResult:
    """Ưu tiên alias era/giai đoạn (khớp tên dài nhất) rồi mới tới năm/thế kỷ nói thẳng trong câu."""
    from hgr.process.normalize import parse_time  # tránh import vòng (normalize không cần period_rules)

    max_year = get_settings().scope.max_year
    matches = find_by_alias(question)
    time_range: tuple[int, int] | None = None
    period_ids: list[str] = []

    if matches:
        best = matches[0]
        time_range = (best.start, best.end)
        if isinstance(best, Period):
            period_ids = [best.id]
        elif isinstance(best, Era):
            period_ids = [p.id for p in best.periods]
    else:
        spans = parse_time(question)
        if spans:
            span = spans[0]
            time_range = (span.start, span.end)
            period_ids = [p.id for p in periods_for_range(span.start, span.end)]

    out_of_scope = time_range is not None and time_range[0] > max_year
    return RuleResult(time_range=time_range, periods=period_ids, out_of_scope=out_of_scope)
