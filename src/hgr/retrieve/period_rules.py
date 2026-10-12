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


# Các cụm từ chắc chắn nằm ngoài phạm vi lịch sử Việt Nam (tiền sử → 1945)
OUT_OF_SCOPE_KEYWORDS = [
    # Sau 1945
    "chiến tranh việt nam",
    "kháng chiến chống mỹ",
    "chống mỹ",
    "việt nam hóa chiến tranh",
    "chiến tranh cục bộ",
    "chiến dịch hồ chí minh",
    "điện biên phủ trên không",
    "hiệp định paris",
    "chiến tranh biên giới",
    "chiến tranh việt trung",
    "chiến tranh việt-trung",
    "thống nhất đất nước",
    "giải phóng miền nam",
    "hội nghị giơ-ne-vơ",
    "hội nghị geneva",
    "việt nam cộng hòa",
    "việt nam cộng hoà",
    "tổng thống việt nam",
    # Ngoài phạm vi Việt Nam / quốc tế
    "tổng thống hoa kỳ",
    "tổng thống mỹ",
    "nhà trắng",
    "lầu năm góc",
    "thế chiến 1",
    "thế chiến 2",
    "thế chiến thứ",
    "chiến tranh thế giới",
    # Khoa học công nghệ hiện đại
    "máy tính",
    "computer",
    "internet",
    "điện thoại thông minh",
    "smartphone",
    "trí tuệ nhân tạo",
    "mạng xã hội",
    "phát minh",
    # Các chủ đề hiện đại
    "điện thoại",
    "tỉnh thành",
    "Việt Nam hiện nay",
    "thành phố trực thuộc",
    "thủ tướng việt nam",
    "thủ tướng",
]


def _is_out_of_scope_text(text: str) -> bool:
    norm = text.lower()
    for kw in OUT_OF_SCOPE_KEYWORDS:
        if kw in norm:
            return True
    return False


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

    out_of_scope = False
    if time_range is not None and time_range[0] > max_year:
        out_of_scope = True
    elif _is_out_of_scope_text(question):
        out_of_scope = True

    return RuleResult(time_range=time_range, periods=period_ids, out_of_scope=out_of_scope)

