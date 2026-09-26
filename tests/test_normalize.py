"""Test process/normalize.py (PLAN.md Mục 3.3)."""
import pytest

from hgr.process.normalize import canchi_years, normalize_text, parse_time, roman_to_int


def spans(text, hint=None):
    return [(s.start, s.end, s.precision) for s in parse_time(text, hint)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("năm 938", [(938, 938, "year")]),
        ("179 TCN", [(-179, -179, "year")]),
        ("năm 208 trước Công nguyên", [(-208, -208, "year")]),
        ("thế kỷ III TCN", [(-300, -201, "century")]),
        ("thế kỷ XIII", [(1201, 1300, "century")]),
        ("cuối thế kỷ XVIII", [(1767, 1800, "century_part")]),
        ("nửa đầu thế kỷ XV", [(1401, 1450, "century_part")]),
        ("thế kỷ VII đến thế kỷ II trước Công nguyên", [(-700, -101, "century")]),
        ("thiên niên kỷ I TCN", [(-1000, -1, "millennium")]),
        ("cách đây 10.000 năm", [(-8000, -8000, "approx")]),
        ("năm Ất Dậu (1945)", [(1945, 1945, "year")]),
        ("ngày 19 tháng 8 năm 1945", [(1945, 1945, "day")]),
        ("ngày 2/9/1945", [(1945, 1945, "day")]),
        ("niên hiệu Hồng Đức thứ 14", [(1483, 1483, "year")]),
        ("Khởi nghĩa Hai Bà Trưng (40–43)", [(40, 43, "year")]),
        ("Âu Lạc (257–179 TCN)", [(-257, -179, "year")]),
        ("Bắc thuộc lần 1 (179 TCN – 40)", [(-179, 40, "year")]),
        ("từ năm 1009 đến năm 1225", [(1009, 1225, "year")]),
        ("Ngô Quyền (897 – 944)", [(897, 944, "year")]),
        ("những năm 1930", [(1930, 1939, "decade")]),
    ],
)
def test_parse_time(text, expected):
    assert spans(text) == expected


def test_legendary_year():
    [span] = parse_time("khoảng 2879 TCN")
    assert (span.start, span.legendary) == (-2879, True)
    [span] = parse_time("khoảng 700 TCN")
    assert span.legendary is False


def test_canchi_needs_period_hint():
    assert spans("tháng Chạp năm Mậu Thân") == []
    assert spans("tháng Chạp năm Mậu Thân", hint=(1771, 1802)) == [(1788, 1788, "year")]
    assert canchi_years("Ất", "Dậu", 1900, 1950) == [1945]


def test_duplicate_nien_hieu_uses_hint():
    assert spans("Thuận Thiên thứ 2") == []  # Lý Thái Tổ (1010) hay Lê Thái Tổ (1428)?
    assert spans("Thuận Thiên thứ 2", hint=(1009, 1225)) == [(1011, 1011, "year")]


def test_numbers_that_are_not_years():
    assert spans("20.000 quân, 5.000-10.000 quân, năm 18 tuổi, hơn 1000 năm, 5-10 thuyền") == []


def test_roman_to_int():
    assert roman_to_int("XVIII") == 18
    assert roman_to_int("XIV") == 14
    with pytest.raises(ValueError):
        roman_to_int("ABC")


def test_normalize_text_tone_marks():
    assert normalize_text("Hoà Bình, thuý, Thuỷ") == "Hòa Bình, thúy, Thủy"
    assert normalize_text("quý, hoàn, khoảng") == "quý, hoàn, khoảng"
