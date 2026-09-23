"""Chuẩn hóa: NFC, dấu thanh, parse thời gian đa dạng (PLAN.md Mục 3.3). (M3)"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


@dataclass
class TimeSpan:
    start: int | None
    end: int | None
    precision: str  # day | year | decade | century | century_part | millennium | approx
    legendary: bool = False


def parse_time(text: str, period_hint: tuple[int, int] | None = None) -> list[TimeSpan]:
    """"179 TCN", "thế kỷ III TCN", "cuối thế kỷ XVIII", can chi, niên hiệu, "2/9/1945"…"""
    raise NotImplementedError


def roman_to_int(s: str) -> int:
    raise NotImplementedError
