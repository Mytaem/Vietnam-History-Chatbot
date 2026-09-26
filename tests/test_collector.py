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
