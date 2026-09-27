"""Test phần logic thuần của ingest/collector.py (không gọi mạng)."""
import pytest

from hgr.ingest.collector import assign_period, assign_tier, resolve_profile


def test_resolve_profile():
    assert len(resolve_profile("mini")[1]) == 32
    assert [p.id for p in resolve_profile("period:tran")[1]] == ["tran"]
    assert {p.era_id for p in resolve_profile("era:candai")[1]} == {"candai"}
    with pytest.raises(ValueError):
        resolve_profile("era:khongco")


def test_assign_period_seed_wins():
    primary, ids = assign_period({"seed_period": "champa", "start_year": 1360, "end_year": 1390})
    assert primary == "champa"
    assert {"tran", "champa"} <= set(ids)


def test_assign_period_largest_overlap_prefers_narrow():
    # Trần Thủ Độ 1194–1264: giao Lý 32 năm, Trần 40 năm
    assert assign_period({"start_year": 1194, "end_year": 1264})[0] == "tran"
    # Chế Bồng Nga 1360–1390 giao đều Trần và Chăm Pa → chọn period hẹp hơn nếu không có gợi ý
    assert assign_period({"start_year": 1360, "end_year": 1390})[0] == "tran"
    assert assign_period({"start_year": 1360, "end_year": 1390, "hint_periods": ["champa"]})[0] == "champa"


def test_assign_period_without_years_uses_hint():
    assert assign_period({"start_year": None, "hint_periods": ["ngo"]}) == ("ngo", ["ngo"])
    assert assign_period({"start_year": None}) == (None, [])


def test_assign_tier_seeds_first_then_in_links():
    articles = [
        {"title": "B", "is_seed": False, "in_links": 5},
        {"title": "A", "is_seed": True, "seed_rank": 1},
        {"title": "C", "is_seed": False, "in_links": 9},
        {"title": "S", "is_seed": True, "seed_rank": 0},
    ]
    assign_tier(articles, quota=3)
    assert {a["title"]: a["tier"] for a in articles} == {"S": "A", "A": "A", "C": "A", "B": "B"}


def test_hinted_main_line_beats_hinted_parallel_branch():
    # Nhà Hậu Lê 1428–1789 được link từ cả seed Chăm Pa lẫn seed Lê sơ: không được rơi vào nhánh song song
    article = {"start_year": 1428, "end_year": 1789, "hint_periods": ["champa", "leso", "trinhnguyen"]}
    assert assign_period(article)[0] in {"leso", "trinhnguyen"}


def test_invalid_and_text_years():
    from hgr.ingest.collector import _text_years, _too_young, _valid_years

    assert _valid_years(2825, 2520) == (None, None)  # Âu Cơ: Wikidata thiếu dấu âm
    assert _valid_years(897, 944) == (897, 944)
    lead = lambda text: {"_parsed": {"sections": [{"path": "Mở đầu", "text": text}]}}
    assert _text_years(lead("Ngô Quyền (chữ Hán: 吳權; 897 – 944) là vua. Mất năm 944.")) == (897, 944)
    assert _text_years(lead("Văn hóa Đồng Đậu được phát hiện năm 1962 ở Vĩnh Phúc.")) == (None, None)
    assert _too_young({"p31": ["Q5"], "times": {"P569": [(1937, 1937)]}}, 1945, 18)
    assert not _too_young({"p31": ["Q5"], "times": {"P569": [(1890, 1890)]}}, 1945, 18)


def test_rank_hints_by_link_count_then_main_line():
    from collections import Counter

    from hgr.ingest.collector import _rank_hints

    assert _rank_hints(Counter({"ly": 1, "phap_xamluoc": 5, "canvuong": 3})) == ["phap_xamluoc", "canvuong", "ly"]
    assert _rank_hints(Counter({"champa": 2, "tran": 2}))[0] == "tran"


def test_assign_tier_prefers_dated_expansions():
    articles = [
        {"title": "Vũng Tàu", "is_seed": False, "in_links": 9, "start_year": None},
        {"title": "Trần Phú", "is_seed": False, "in_links": 2, "start_year": 1904},
    ]
    assign_tier(articles, quota=1)
    assert {a["title"]: a["tier"] for a in articles} == {"Trần Phú": "A", "Vũng Tàu": "B"}


def test_useful_alias_filters_collision_prone_aliases():
    from hgr.ingest.collector import _useful_alias

    for junk in ["Lin", "N.", "T.L.", "N.A.Q", "A.P", "Line | Chettha", "Hồ Chí Minh"]:
        assert not _useful_alias(junk, "Hồ Chí Minh"), junk
    for good in ["Nguyễn Ái Quốc", "Nguyễn Tất Thành", "Ho Chi Minh", "Bác Hồ"]:
        assert _useful_alias(good, "Hồ Chí Minh"), good
