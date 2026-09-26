"""Test hgr.periods (M2)."""
from hgr.periods import Period, find_by_alias, load_eras, overlaps, periods_for_range


def test_overlaps_basic():
    assert overlaps(1225, 1400, 1288, 1288)
    assert not overlaps(1225, 1400, 1401, 1500)
    assert overlaps(-179, 40, -111, None)


def test_load_eras():
    eras = load_eras()
    assert len(eras) == 6  # tiensu, dungnuoc, bacthuoc, songsong, phongkien, candai
    total_periods = sum(len(e.periods) for e in eras)
    assert total_periods == 32  # 29 giai đoạn chính + 3 nhánh song song
    assert all(isinstance(p, Period) for e in eras for p in e.periods)


def test_alias_lookup_era():
    matches = find_by_alias("Kể tôi nghe về thời Bắc thuộc.")
    assert matches
    assert matches[0].id == "bacthuoc"
    assert (matches[0].start, matches[0].end) == (-179, 938)


def test_alias_lookup_period_longest_match_wins():
    matches = find_by_alias("Bắc thuộc lần 2 diễn ra thế nào?")
    assert matches
    assert matches[0].id == "bacthuoc_2"
    assert (matches[0].start, matches[0].end) == (43, 544)


def test_alias_lookup_no_match():
    assert find_by_alias("Hôm nay trời đẹp quá") == []


def test_periods_for_range_includes_parallel_branch():
    ids = {p.id for p in periods_for_range(1300, 1300)}
    assert "tran" in ids
    assert "champa" in ids


def test_periods_for_range_out_of_scope():
    assert periods_for_range(1954, 1954) == []
