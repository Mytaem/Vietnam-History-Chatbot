"""Phân kỳ lịch sử: load configs/periods.yaml, tra alias, tính overlap năm (PLAN.md Mục 2)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Period:
    id: str
    name: str
    era_id: str
    start: int
    end: int
    aliases: list[str] = field(default_factory=list)
    parallel: bool = False
    legendary: bool = False
    disputed: bool = False
    alt_start: int | None = None
    alt_end: int | None = None
    tier_a_quota: int = 0
    seed_titles: list[str] = field(default_factory=list)
    seed_categories: list[str] = field(default_factory=list)
    role_vocab: list[str] = field(default_factory=list)
    polities: list[str] = field(default_factory=list)


@dataclass
class Era:
    id: str
    name: str
    start: int
    end: int
    color: str
    aliases: list[str] = field(default_factory=list)
    parallel: bool = False
    periods: list[Period] = field(default_factory=list)


def load_eras(path: str | None = None) -> list[Era]:
    """Đọc periods.yaml → danh sách Era (kèm Period). TODO(M2)."""
    raise NotImplementedError


def overlaps(a_start: int, a_end: int | None, b_start: int, b_end: int | None) -> bool:
    """Hai khoảng năm có giao nhau không (end=None → bằng start)."""
    a_end = a_start if a_end is None else a_end
    b_end = b_start if b_end is None else b_end
    return a_start <= b_end and a_end >= b_start


def find_by_alias(text: str) -> list[Period | Era]:
    """Tìm era/period được nhắc trong câu (ưu tiên khớp dài nhất). TODO(M2)."""
    raise NotImplementedError


def periods_for_range(start: int, end: int) -> list[Period]:
    """Các period (kể cả nhánh song song) giao với khoảng năm. TODO(M2)."""
    raise NotImplementedError
