"""Test extract/validator.py (chạy được độc lập, không cần Neo4j hay Ollama)."""
from __future__ import annotations

import unicodedata
import pytest

from hgr.extract.validator import (
    get_rejection_stats,
    load_ontology,
    record_reject,
    validate_triplet,
)


def test_validate_triplet_accepts_good_record():
    """Test cơ bản nguyên bản: bản ghi hợp lệ trong khoảng năm và có bằng chứng."""
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
    """Test nguyên bản được cập nhật để kiểm tra các mã lý do chuẩn hóa."""
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
    # Kiểm tra tương thích với assert cũ (tìm chữ 'confidence' trong mã lý do 'low_confidence')
    assert any("confidence" in reason.lower() for reason in result["reasons"])
    # Kiểm tra các mã lý do chuẩn hóa ngắn
    assert "after_1945" in result["reasons"]
    assert "low_confidence" in result["reasons"]
    assert "tail_type_invalid" in result["reasons"]


def test_evidence_short_sentence_in_long_chunk_accepted():
    """Evidence là một câu ngắn nằm nguyên văn trong chunk dài: chấp nhận."""
    long_chunk = (
        "Lý Thường Kiệt (1019 – 1105) là một nhà quân sự, chính trị lỗi lạc của triều Lý nước Đại Việt. "
        "Năm 1077, ông chỉ huy quân đội Đại Việt đánh bại quân xâm lược nhà Tống trên phòng tuyến sông Như Nguyệt. "
        "Chiến thắng này đã đè bẹp ý chí xâm lược của nhà Tống, giữ vững nền độc lập cho Đại Việt."
    )
    triplet = {
        "head": "Lý Thường Kiệt",
        "relation": "COMMANDED",
        "tail": "Trận Như Nguyệt",
        "start_year": 1077,
        "end_year": 1077,
        "evidence": "Năm 1077, ông chỉ huy quân đội Đại Việt đánh bại quân xâm lược nhà Tống trên phòng tuyến sông Như Nguyệt.",
        "confidence": 0.95,
    }
    entities = {"Lý Thường Kiệt": "Person", "Trận Như Nguyệt": "Event"}
    result = validate_triplet(triplet, entities, long_chunk)
    assert result["ok"] is True
    assert result["reasons"] == []


def test_evidence_loose_whitespace_and_case_accepted():
    """Evidence lệch nhẹ (khác khoảng trắng thừa, viết hoa/viết thường): chấp nhận."""
    chunk = "Trần Hưng Đạo lãnh đạo nhân dân ba lần đánh tan quân Nguyên Mông xâm lược."
    evidence_loose = "  trần  hưng  đạo   lãnh ĐẠO nhân dân ba lần đánh tan quân nguyên mông xâm lược.  "
    triplet = {
        "head": "Trần Hưng Đạo",
        "relation": "COMMANDED",
        "tail": "Chiến tranh Nguyên Mông – Đại Việt",
        "evidence": evidence_loose,
        "confidence": 0.9,
    }
    entities = {"Trần Hưng Đạo": "Person", "Chiến tranh Nguyên Mông – Đại Việt": "Event"}
    result = validate_triplet(triplet, entities, chunk)
    assert result["ok"] is True
    assert result["reasons"] == []


def test_evidence_nfd_normalized_to_nfc_accepted():
    """Evidence dùng mã hóa NFD (ký tự tổ hợp) so với chunk dùng NFC (dựng sẵn): chấp nhận."""
    evidence_str = "Quang Trung đại phá quân Thanh vào dịp Tết Kỷ Dậu năm 1789."
    chunk_nfc = unicodedata.normalize("NFC", f"Đầu xuân, {evidence_str} Sau đó giải phóng Thăng Long.")
    evidence_nfd = unicodedata.normalize("NFD", evidence_str)

    assert evidence_nfd != unicodedata.normalize("NFC", evidence_nfd)  # Xác nhận byte representation lệch nhau

    triplet = {
        "head": "Quang Trung",
        "relation": "COMMANDED",
        "tail": "Trận Ngọc Hồi – Đống Đa",
        "evidence": evidence_nfd,
        "confidence": 0.9,
    }
    entities = {"Quang Trung": "Person", "Trận Ngọc Hồi – Đống Đa": "Event"}
    result = validate_triplet(triplet, entities, chunk_nfc)
    assert result["ok"] is True
    assert result["reasons"] == []


def test_evidence_not_in_chunk_rejected():
    """Evidence bịa hoặc không có trong chunk: loại với mã evidence_not_in_chunk."""
    chunk = "Ngô Quyền đánh tan quân Nam Hán trên sông Bạch Đằng năm 938."
    triplet = {
        "head": "Ngô Quyền",
        "relation": "COMMANDED",
        "tail": "Trận Bạch Đằng (938)",
        "evidence": "Lê Lợi chỉ huy khởi nghĩa Lam Sơn toàn thắng.",
        "confidence": 0.85,
    }
    result = validate_triplet(triplet, chunk)
    assert result["ok"] is False
    assert "evidence_not_in_chunk" in result["reasons"]


def test_relation_not_in_ontology_rejected():
    """Quan hệ không tồn tại trong configs/ontology.yaml: loại với mã relation_not_in_ontology."""
    chunk = "Hai Bà Trưng cưỡi voi ra trận."
    triplet = {
        "head": "Trưng Trắc",
        "relation": "INVENTED_RELATION",
        "tail": "Voi",
        "evidence": "Hai Bà Trưng cưỡi voi ra trận.",
        "confidence": 0.8,
    }
    result = validate_triplet(triplet, chunk)
    assert result["ok"] is False
    assert "relation_not_in_ontology" in result["reasons"]


def test_head_or_tail_type_invalid_rejected():
    """Kiểu head hoặc tail sai ontology (ví dụ COMMANDED có head là Place, tail là Place): loại."""
    chunk = "Hoa Lư chỉ huy Trận Bạch Đằng tại sông Bạch Đằng."
    # 1. COMMANDED yêu cầu domain: [Person], nếu head là Place -> head_type_invalid
    triplet_bad_head = {
        "head": "Hoa Lư",
        "relation": "COMMANDED",
        "tail": "Trận Bạch Đằng",
        "evidence": "Hoa Lư chỉ huy Trận Bạch Đằng tại sông Bạch Đằng.",
        "confidence": 0.8,
    }
    entities_head = {"Hoa Lư": "Place", "Trận Bạch Đằng": "Event"}
    res1 = validate_triplet(triplet_bad_head, entities_head, chunk)
    assert res1["ok"] is False
    assert "head_type_invalid" in res1["reasons"]

    # 2. COMMANDED yêu cầu range: [Event], nếu tail là Place -> tail_type_invalid
    triplet_bad_tail = {
        "head": "Ngô Quyền",
        "relation": "COMMANDED",
        "tail": "Sông Bạch Đằng",
        "evidence": "Hoa Lư chỉ huy Trận Bạch Đằng tại sông Bạch Đằng.",
        "confidence": 0.8,
    }
    entities_tail = {"Ngô Quyền": "Person", "Sông Bạch Đằng": "Place"}
    res2 = validate_triplet(triplet_bad_tail, entities_tail, chunk)
    assert res2["ok"] is False
    assert "tail_type_invalid" in res2["reasons"]


def test_event_after_1945_rejected():
    """Triplet có năm bắt đầu sau mốc cắt 1945: loại với mã after_1945."""
    chunk = "Năm 1954 diễn ra chiến dịch Điện Biên Phủ lịch sử."
    triplet = {
        "head": "Võ Nguyên Giáp",
        "relation": "COMMANDED",
        "tail": "Chiến dịch Điện Biên Phủ",
        "start_year": 1954,
        "evidence": "Năm 1954 diễn ra chiến dịch Điện Biên Phủ lịch sử.",
        "confidence": 0.9,
    }
    result = validate_triplet(triplet, chunk)
    assert result["ok"] is False
    assert "after_1945" in result["reasons"]


def test_record_reject_and_get_stats(tmp_path):
    """Ghi triplet bị loại và hàm get_rejection_stats đếm thống kê chính xác."""
    reject_file = tmp_path / "rejects.jsonl"

    t1 = {"head": "A", "relation": "BAD_REL", "tail": "B"}
    record_reject(t1, ["relation_not_in_ontology"], chunk_id="chk-01", reject_path=reject_file)

    t2 = {"head": "C", "relation": "COMMANDED", "tail": "D", "start_year": 1975}
    record_reject(t2, ["after_1945", "evidence_not_in_chunk"], chunk_id="chk-02", reject_path=reject_file)

    t3 = {"head": "E", "relation": "COMMANDED", "tail": "F", "start_year": 1980}
    record_reject(t3, ["after_1945"], chunk_id="chk-03", reject_path=reject_file)

    stats = get_rejection_stats(reject_path=reject_file)
    assert stats["relation_not_in_ontology"] == 1
    assert stats["after_1945"] == 2
    assert stats["evidence_not_in_chunk"] == 1

    # Kiểm tra cờ record_rejects=True trong validate_triplet
    bad_trip = {
        "head": "X",
        "relation": "UNKNOWN_REL",
        "tail": "Y",
        "evidence": "không có trong đoạn",
    }
    res = validate_triplet(
        bad_trip,
        chunk_text="Một đoạn văn bất kỳ",
        chunk_id="chk-04",
        record_rejects=True,
        reject_path=reject_file,
    )
    assert res["ok"] is False
    stats_updated = get_rejection_stats(reject_path=reject_file)
    assert stats_updated["relation_not_in_ontology"] == 2
    assert stats_updated["evidence_not_in_chunk"] == 2


def test_load_ontology_missing_file_raises_error(tmp_path):
    """File ontology không tồn tại phải ném FileNotFoundError rõ ràng."""
    missing_file = tmp_path / "nonexistent_ontology.yaml"
    with pytest.raises(FileNotFoundError, match="Không tìm thấy file ontology"):
        load_ontology(missing_file)
