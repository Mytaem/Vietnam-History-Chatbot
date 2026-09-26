"""Phân kỳ lịch sử: load configs/periods.yaml, tra alias, tính overlap năm (PLAN.md Mục 2)."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from hgr.config import CONFIG_DIR


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

    @property
    def names(self) -> list[str]:
        return [self.name, *self.aliases]


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

    @property
    def names(self) -> list[str]:
        return [self.name, *self.aliases]


def _normalize(text: str) -> str:
    """NFC + casefold để so khớp không phân biệt hoa/thường và không lệch dấu."""
    return unicodedata.normalize("NFC", text).casefold()


def _period_from_dict(raw: dict, era_id: str) -> Period:
    return Period(
        id=raw["id"],
        name=raw["name"],
        era_id=era_id,
        start=raw["start"],
        end=raw["end"],
        aliases=raw.get("aliases", []),
        parallel=raw.get("parallel", False),
        legendary=raw.get("legendary", False),
        disputed=raw.get("disputed", False),
        alt_start=raw.get("alt_start"),
        alt_end=raw.get("alt_end"),
        tier_a_quota=raw.get("tier_a_quota", 0),
        seed_titles=raw.get("seed_titles", []),
        seed_categories=raw.get("seed_categories", []),
        role_vocab=raw.get("role_vocab", []),
        polities=raw.get("polities", []),
    )


@lru_cache
def load_eras(path: str | Path = CONFIG_DIR / "periods.yaml") -> list[Era]:
    """Đọc periods.yaml → danh sách Era (kèm Period)."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    eras = []
    for raw in data["eras"]:
        era = Era(
            id=raw["id"],
            name=raw["name"],
            start=raw["start"],
            end=raw["end"],
            color=raw.get("color", "#888888"),
            aliases=raw.get("aliases", []),
            parallel=raw.get("parallel", False),
        )
        era.periods = [_period_from_dict(p, era.id) for p in raw.get("periods", [])]
        eras.append(era)
    return eras


def all_periods() -> list[Period]:
    """Danh sách phẳng mọi period (kể cả nhánh song song), theo đúng thứ tự khai báo trong file."""
    return [p for era in load_eras() for p in era.periods]


def overlaps(a_start: int, a_end: int | None, b_start: int, b_end: int | None) -> bool:
    """Hai khoảng năm có giao nhau không (end=None → bằng start)."""
    a_end = a_start if a_end is None else a_end
    b_end = b_start if b_end is None else b_end
    return a_start <= b_end and a_end >= b_start


def find_by_alias(text: str) -> list[Period | Era]:
    """Tìm era/period được nhắc trong câu (ưu tiên khớp dài nhất)."""
    haystack = _normalize(text)
    matches: list[tuple[int, Period | Era]] = []
    seen_ids: set[str] = set()

    def _consider(obj: Period | Era) -> None:
        if obj.id in seen_ids:
            return
        best_len = 0
        for name in obj.names:
            needle = _normalize(name)
            if needle and needle in haystack:
                best_len = max(best_len, len(needle))
        if best_len:
            matches.append((best_len, obj))
            seen_ids.add(obj.id)

    for era in load_eras():
        for period in era.periods:
            _consider(period)
        _consider(era)

    matches.sort(key=lambda pair: pair[0], reverse=True)
    return [obj for _, obj in matches]


def periods_for_range(start: int, end: int | None = None) -> list[Period]:
    """Các period (kể cả nhánh song song) giao với khoảng năm."""
    return [p for p in all_periods() if overlaps(p.start, p.end, start, end)]


def find_gaps() -> list[tuple[int, int]]:
    """Khoảng năm nào không được period nào trên trục chính (không tính nhánh song song) phủ tới.

    Gộp các khoảng năm chồng/liền kề rồi tìm lỗ hổng ở giữa. Dùng cho `hgr periods --check`.
    """
    intervals = sorted((p.start, p.end) for p in all_periods() if not p.parallel)
    gaps: list[tuple[int, int]] = []
    if not intervals:
        return gaps
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start > cur_end + 1:
            gaps.append((cur_end + 1, start - 1))
            cur_end = end
        else:
            cur_end = max(cur_end, end)
    return gaps
