"""Test hgr.periods (M2). overlaps() đã chạy được; phần còn lại chờ load_eras()."""
import pytest

from hgr.periods import overlaps


def test_overlaps_basic():
    assert overlaps(1225, 1400, 1288, 1288)
    assert not overlaps(1225, 1400, 1401, 1500)
    assert overlaps(-179, 40, -111, None)


@pytest.mark.todo
def test_alias_lookup():
    """TODO(M2): "thời Bắc thuộc" → [-179, 938]; "Bắc thuộc lần 2" → [43, 544]."""
