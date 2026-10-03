"""Test retrieve/period_rules.py (PLAN.md Mục 6.3, bảng A0)."""
from hgr.retrieve.period_rules import parse


def test_era_alias():
    assert parse("Kể về thời Bắc thuộc").time_range == (-179, 938)


def test_period_alias_longest_match():
    r = parse("Bắc thuộc lần 2 diễn ra thế nào?")
    assert r.time_range == (43, 544)
    assert r.periods == ["bacthuoc_2"]


def test_french_colonial_era():
    assert parse("thời Pháp thuộc có gì nổi bật?").time_range == (1858, 1945)


def test_century():
    assert parse("Nói về thế kỷ XV").time_range == (1401, 1500)


def test_out_of_scope_after_1945():
    r = parse("Chuyện gì xảy ra sau năm 1954?")
    assert r.out_of_scope is True
    assert r.time_range == (1954, 1954)


def test_no_time_signal():
    r = parse("Trần Hưng Đạo là ai?")
    assert r.time_range is None
    assert r.periods == []
    assert r.out_of_scope is False
