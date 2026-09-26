"""Chuẩn hóa: NFC, dấu thanh, parse thời gian đa dạng (PLAN.md Mục 3.3). (M3)"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import yaml

from hgr.config import CONFIG_DIR

MIN_YEAR, MAX_YEAR = -40000, 2100


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


# Dấu thanh kiểu mới (hoà, thuý) → kiểu cũ (hòa, thúy) như Wikipedia tiếng Việt, chỉ ở cuối âm tiết.
_TONE_PAIRS = {
    "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
    "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
    "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
}
_TONE_PAIRS.update({k.capitalize(): v.capitalize() for k, v in list(_TONE_PAIRS.items())})
_TONE_RE = re.compile(r"(?<![qQ])(" + "|".join(_TONE_PAIRS) + r")(?![^\W\d_])")


def normalize_text(text: str) -> str:
    """NFC + đưa dấu thanh về kiểu cũ, để văn bản Wiki, output LLM và câu hỏi so khớp được với nhau."""
    return _TONE_RE.sub(lambda m: _TONE_PAIRS[m.group(1)], nfc(text))


@dataclass
class TimeSpan:
    start: int | None
    end: int | None
    precision: str  # day | year | decade | century | century_part | millennium | approx
    legendary: bool = False


_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str) -> int:
    s = s.strip().upper()
    if not s or any(ch not in _ROMAN for ch in s):
        raise ValueError(f"Không phải số La Mã: {s!r}")
    total = 0
    for i, ch in enumerate(s):
        value = _ROMAN[ch]
        if i + 1 < len(s) and _ROMAN[s[i + 1]] > value:
            total -= value
        else:
            total += value
    return total


CAN = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
CHI = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]
_CAN_INDEX = {c.lower(): i for i, c in enumerate(CAN)} | {"kỉ": 5, "quí": 9}
_CHI_INDEX = {c.lower(): i for i, c in enumerate(CHI)} | {"tí": 0, "mẹo": 3, "tị": 5}


def canchi_years(can: str, chi: str, lo: int, hi: int) -> list[int]:
    """Các năm trong [lo, hi] có can chi tương ứng (năm TCN âm, không có năm 0)."""
    ci, zi = _CAN_INDEX[can.lower()], _CHI_INDEX[chi.lower()]
    years = []
    for y in range(lo, hi + 1):
        if y == 0:
            continue
        astro = y if y > 0 else y + 1
        if (astro - 4) % 10 == ci and (astro - 4) % 12 == zi:
            years.append(y)
    return years


@lru_cache
def _nien_hieu() -> dict[str, list[int]]:
    with open(CONFIG_DIR / "backbone" / "nien_hieu.yaml", encoding="utf-8") as f:
        rows = yaml.safe_load(f)["nien_hieu"]
    table: dict[str, list[int]] = {}
    for row in rows:
        table.setdefault(nfc(row["name"]).lower(), []).append(row["start"])
    return table


_ORDINALS = {"nhất": 1, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5, "sáu": 6,
             "bảy": 7, "tám": 8, "chín": 9, "mười": 10}

_BCE_INNER = r"\s*(?:TCN|tr\.\s?CN|trước\s+(?:công\s+nguyên|CN))"
_BCE = rf"(?P<bce>{_BCE_INNER})"
_NUM = r"\d{1,3}(?:[.,]\d{3})+|\d+"
_CENT = r"(?-i:[IVXLCDM]+)(?![^\W\d_])|\d{1,2}(?!\d)"
_CAN_RE = "|".join(sorted(_CAN_INDEX, key=len, reverse=True))
_CHI_RE = "|".join(sorted(_CHI_INDEX, key=len, reverse=True))
_APPROX = r"(?P<approx>(?:vào\s+)?(?:khoảng|chừng|độ)\s+)?"
_NOT_DIGIT_AFTER = r"(?![\d.,]?\d)"
_FLAGS = re.IGNORECASE


def _int(num: str) -> int:
    return int(re.sub(r"[.,]", "", num))


def _signed(num: str, bce: bool) -> int:
    return -_int(num) if bce else _int(num)


def _century_number(token: str) -> int:
    return int(token) if token.isdigit() else roman_to_int(token)


def _century_bounds(c: int, bce: bool) -> tuple[int, int]:
    return (-(c * 100), -((c - 1) * 100 + 1)) if bce else ((c - 1) * 100 + 1, c * 100)


def _century_part(lo: int, hi: int, part: str) -> tuple[int, int]:
    part = " ".join(part.lower().split())
    if part == "đầu":
        return lo, lo + 32
    if part == "giữa":
        return lo + 33, lo + 65
    if part == "cuối":
        return lo + 66, hi
    if part == "nửa đầu":
        return lo, lo + 49
    return lo + 50, hi  # nửa sau / nửa cuối


def _parse_full_date(m: re.Match, hint) -> TimeSpan | None:
    if not (1 <= int(m.group("d")) <= 31 and 1 <= int(m.group("m")) <= 12):
        return None
    year = _signed(m.group("y"), bool(m.groupdict().get("bce")))
    return TimeSpan(year, year, "day")


def _parse_month_year(m: re.Match, hint) -> TimeSpan | None:
    if not 1 <= int(m.group("m")) <= 12:
        return None
    year = _signed(m.group("y"), bool(m.group("bce")))
    return TimeSpan(year, year, "year")


def _parse_millennium(m: re.Match, hint) -> TimeSpan | None:
    n = _century_number(m.group("n"))
    if m.group("bce"):
        return TimeSpan(-(n * 1000), -((n - 1) * 1000 + 1), "millennium")
    return TimeSpan((n - 1) * 1000 + 1, n * 1000, "millennium")


def _parse_century(m: re.Match, hint) -> TimeSpan | None:
    bce = bool(m.group("bce"))
    lo, hi = _century_bounds(_century_number(m.group("c1")), bce)
    if m.group("c2"):
        lo2, hi2 = _century_bounds(_century_number(m.group("c2")), bce)
        return TimeSpan(min(lo, lo2), max(hi, hi2), "century")
    if m.group("part"):
        lo, hi = _century_part(lo, hi, m.group("part"))
        return TimeSpan(lo, hi, "century_part")
    return TimeSpan(lo, hi, "century")


def _parse_decade(m: re.Match, hint) -> TimeSpan | None:
    start = int(m.group("y"))
    return TimeSpan(start, start + 9, "decade")


def _parse_ago(m: re.Match, hint) -> TimeSpan | None:
    a = _int(m.group("a"))
    b = _int(m.group("b")) if m.group("b") else a
    return TimeSpan(2000 - max(a, b), 2000 - min(a, b), "approx")


def _parse_paren_year(m: re.Match, hint) -> TimeSpan | None:
    year = _signed(m.group("y"), bool(m.group("bce")))
    return TimeSpan(year, year, "year")


def _parse_nien_hieu(m: re.Match, hint) -> TimeSpan | None:
    starts = _nien_hieu().get(nfc(m.group("name")).lower(), [])
    token = " ".join(m.group("n").lower().split())
    if token.startswith("nguyên"):
        n = 1
    else:
        token = token.removeprefix("thứ").strip()
        n = int(token) if token.isdigit() else _ORDINALS.get(token)
    if not starts or not n:
        return None
    years = [s + n - 1 for s in starts]
    if len(years) > 1 and hint:
        years = [y for y in years if hint[0] <= y <= hint[1]]
    return TimeSpan(years[0], years[0], "year") if len(years) == 1 else None


def _parse_canchi(m: re.Match, hint) -> TimeSpan | None:
    if not hint:
        return None
    years = canchi_years(m.group("can"), m.group("chi"), hint[0], hint[1])
    return TimeSpan(years[0], years[0], "year") if len(years) == 1 else None


def _parse_range(m: re.Match, hint) -> TimeSpan | None:
    a, b = m.group("a"), m.group("b")
    if not m.group("pre") and (len(a) < 3 or len(b) < 3):
        return None
    bce_b = bool(m.group("bb"))
    bce_a = bool(m.group("ba")) or (bce_b and _int(a) > _int(b))
    start, end = _signed(a, bce_a), _signed(b, bce_b)
    return TimeSpan(start, end, "year") if start <= end else None


def _parse_year_bce(m: re.Match, hint) -> TimeSpan | None:
    year = -_int(m.group("y"))
    return TimeSpan(year, year, "approx" if m.group("approx") else "year")


def _parse_year(m: re.Match, hint) -> TimeSpan | None:
    year = int(m.group("y"))
    return TimeSpan(year, year, "approx" if m.groupdict().get("approx") else "year")


@lru_cache
def _patterns() -> list[tuple[re.Pattern, Callable]]:
    nien_hieu = "|".join(re.escape(n) for n in sorted(_nien_hieu(), key=len, reverse=True))
    ordinals = "|".join(_ORDINALS)
    return [
        (rf"(?:ngày\s+)?(?<!\d)(?P<d>\d{{1,2}})\s+tháng\s+(?P<m>\d{{1,2}})\s*,?\s*năm\s+(?P<y>\d{{1,4}}){_BCE}?",
         _parse_full_date),
        (r"(?<![\d/.])(?P<d>\d{1,2})[/.-](?P<m>\d{1,2})[/.-](?P<y>\d{3,4})(?![\d/])", _parse_full_date),
        (rf"tháng\s+(?P<m>\d{{1,2}})\s*(?:/\s*|,?\s*năm\s+)(?P<y>\d{{1,4}})(?!\d){_BCE}?", _parse_month_year),
        (rf"thiên\s+niên\s+kỷ\s+(?:thứ\s+)?(?P<n>{_CENT}){_BCE}?", _parse_millennium),
        (rf"(?:(?P<part>nửa\s+đầu|nửa\s+sau|nửa\s+cuối|đầu|giữa|cuối)\s+)?(?:thế\s+k[ỷỉ]|(?-i:TK))\s+(?:thứ\s+)?"
         rf"(?P<c1>{_CENT})(?:\s*(?:[–—-]|đến|tới)\s*(?:thế\s+k[ỷỉ]\s+)?(?P<c2>{_CENT}))?{_BCE}?",
         _parse_century),
        (r"(?:thập\s+niên|những\s+năm)\s+(?P<y>\d{3}0)(?!\d)", _parse_decade),
        (rf"cách\s+(?:đây|nay)\s+(?:khoảng\s+|chừng\s+|hơn\s+|trên\s+|gần\s+)?(?P<a>{_NUM})"
         rf"(?:\s*[–-]\s*(?P<b>{_NUM}))?\s+năm", _parse_ago),
        (rf"(?:năm\s+)?(?:{_CAN_RE})\s+(?:{_CHI_RE})\s*\(\s*(?:năm\s+)?(?P<y>\d{{1,4}}){_BCE}?\s*\)",
         _parse_paren_year),
        (rf"(?:niên\s+hiệu\s+|năm\s+)?(?P<name>{nien_hieu})\s+(?:năm\s+)?"
         rf"(?P<n>thứ\s+(?:\d{{1,2}}|{ordinals})|nguyên\s+niên)", _parse_nien_hieu),
        (rf"năm\s+(?P<can>{_CAN_RE})\s+(?P<chi>{_CHI_RE})(?![^\W\d_])", _parse_canchi),
        (rf"(?P<pre>từ\s+)(?:năm\s+)?(?P<a>\d{{1,5}})(?P<ba>{_BCE_INNER})?\s+(?:đến|tới)\s+(?:năm\s+)?"
         rf"(?P<b>\d{{1,4}})(?P<bb>{_BCE_INNER})?{_NOT_DIGIT_AFTER}", _parse_range),
        (rf"(?P<pre>\(\s*|năm\s+|giai\s+đoạn\s+|thời\s+kỳ\s+)?(?<![\d.,])(?P<a>\d{{1,5}})(?P<ba>{_BCE_INNER})?"
         rf"\s*[–—-]\s*(?:năm\s+)?(?P<b>\d{{1,4}})(?P<bb>{_BCE_INNER})?{_NOT_DIGIT_AFTER}", _parse_range),
        (rf"{_APPROX}(?:năm\s+)?(?<![\d.,])(?P<y>{_NUM})(?:\s+năm)?{_BCE}", _parse_year_bce),
        (rf"{_APPROX}năm\s+(?P<y>\d{{1,4}}){_NOT_DIGIT_AFTER}(?!\s*tuổi)", _parse_year),
        (rf"\(\s*(?P<y>\d{{3,4}})\s*\)(?P<bce>)", _parse_paren_year),
        (rf"\b(?:từ|đến|tới|vào|sau|trước|cuối|đầu|giữa)\s+(?P<y>\d{{3,4}}){_NOT_DIGIT_AFTER}"
         r"(?!\s*(?:quân|người|năm|km|mét|m\b|tuổi|chiếc|thuyền|lính|dặm|%|ha\b))", _parse_year),
    ]


@lru_cache
def _compiled() -> list[tuple[re.Pattern, Callable]]:
    return [(re.compile(p, _FLAGS), handler) for p, handler in _patterns()]


def _is_legendary(span: TimeSpan) -> bool:
    # Năm lẻ trước Âu Lạc (2879, 2524 TCN…) là niên đại truyền thuyết; mốc khảo cổ thường là số tròn.
    return span.start < -258 and span.precision in ("year", "approx") and span.start % 50 != 0


def parse_time(text: str, period_hint: tuple[int, int] | None = None) -> list[TimeSpan]:
    """"179 TCN", "thế kỷ III TCN", "cuối thế kỷ XVIII", can chi, niên hiệu, "2/9/1945"…"""
    text = nfc(text)
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, TimeSpan]] = []

    for pattern, handler in _compiled():
        for m in pattern.finditer(text):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            span = handler(m, period_hint)
            if span is None:
                continue
            if not (MIN_YEAR <= span.start <= MAX_YEAR and MIN_YEAR <= span.end <= MAX_YEAR):
                continue
            if span.start == 0 or span.end == 0:
                continue
            span.legendary = _is_legendary(span)
            taken.append((m.start(), m.end()))
            found.append((m.start(), span))

    return [span for _, span in sorted(found, key=lambda pair: pair[0])]
