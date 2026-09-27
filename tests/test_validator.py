"""Test extract/validator.py"""
import pytest

from hgr.extract.validator import validate_triplet


def test_validate_triplet_accepts_good_record():
    triplet = {
        "head": "Ngô Quyền",
        "relation": "RULED",
        "tail": "Văn Lang",
        "start_year": 939,
        "end_year": 944,
        "evidence": "Ngô Quyền lên ngôi năm 939.",
        "confidence": 0.9,
    }
    assert validate_triplet(triplet, "Ngô Quyền lên ngôi năm 939.") == {"ok": True, "reasons": []}


def test_validate_triplet_rejects_ill_formed_and_out_of_range():
    triplet = {
        "head": "Ngô Quyền",
        "relation": "RULED",
        "tail": "Hà Nội",
        "start_year": 1950,
        "end_year": 1955,
        "evidence": "Ngô Quyền lên ngôi năm 1950.",
        "confidence": 0.4,
    }
    result = validate_triplet(triplet, "Ngô Quyền lên ngôi năm 939.")
    assert result["ok"] is False
    assert any("năm" in reason.lower() or "confidence" in reason.lower() for reason in result["reasons"])
