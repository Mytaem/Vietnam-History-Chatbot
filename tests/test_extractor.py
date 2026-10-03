"""Test cho extractor.py: cache hit, prompt version change, pass 2 entity passing,

validator reject, chunk fault-tolerance, resume, era filtering, tier S. (M4)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hgr.extract.extractor import ExtractResult, extract_chunk, run, to_json_dict
from hgr.extract.schemas import Entity, EntityOutput, RelationOutput, Triplet
from hgr.llm.cache import DiskCache

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.chat_model = "qwen3:4b-instruct-2507"

    def _chat_json_side_effect(messages, schema):
        if schema is EntityOutput:
            return EntityOutput(
                entities=[
                    Entity(
                        name="Lý Thường Kiệt",
                        type="Person",
                        description="Danh tướng thời Lý",
                    ),
                    Entity(
                        name="Sông Như Nguyệt",
                        type="Place",
                        description="Nơi diễn ra phòng tuyến kháng Tống",
                    ),
                    Entity(
                        name="Trận Như Nguyệt",
                        type="Event",
                        description="Trận chiến phòng thủ trên sông",
                    ),
                ]
            )
        elif schema is RelationOutput:
            return RelationOutput(
                triplets=[
                    Triplet(
                        head="Lý Thường Kiệt",
                        relation="COMMANDED",
                        tail="Trận Như Nguyệt",
                        evidence="Lý Thường Kiệt chỉ huy quân dân đánh tan quân Tống trên sông Như Nguyệt",
                        confidence=0.9,
                    )
                ]
            )
        raise ValueError(f"Unknown schema: {schema}")

    client.chat_json.side_effect = _chat_json_side_effect
    return client


@pytest.fixture
def sample_chunk():
    return {
        "id": "test-chunk-001",
        "text": "Năm 1077, Lý Thường Kiệt chỉ huy quân dân đánh tan quân Tống trên sông Như Nguyệt bảo vệ vẹn toàn bờ cõi Đại Việt.",
        "page_title": "Lý Thường Kiệt",
        "period_id": "ly",
        "era_id": "phongkien",
    }


def test_extract_chunk_cache_hit(tmp_path, mock_client, sample_chunk):
    """Gọi extract_chunk 2 lần cùng chunk: lần 2 cache hit hoàn toàn, không gọi thêm client.chat_json."""
    cache = DiskCache(tmp_path / "cache")

    # Lần 1: Gọi LLM cho cả Pass 1 và Pass 2
    res1 = extract_chunk(sample_chunk, client=mock_client, cache=cache)
    assert isinstance(res1, ExtractResult)
    assert len(res1.entities) == 3
    assert len(res1.triplets) == 1
    # Truy cập thuộc tính tường minh thay vì unpack ngầm
    ents = res1.entities
    trips = res1.triplets
    assert len(ents) == 3
    assert len(trips) == 1
    assert mock_client.chat_json.call_count == 2
    assert res1.cache_hit is False

    # Kiểm tra serialization to_dict() và to_json_dict()
    d1 = res1.to_dict()
    assert d1 == to_json_dict(res1)
    assert d1["chunk_id"] == sample_chunk["id"]
    assert d1["entities"] == res1.entities
    assert d1["triplets"] == res1.triplets
    assert d1["rejects"] == res1.rejects
    assert d1["cache_hit"] is False

    # Không còn hỗ trợ unpack ngầm thành iterable tuple
    with pytest.raises(TypeError):
        _ = [item for item in res1]

    # Lần 2: Cache hit cả 2 pass
    res2 = extract_chunk(sample_chunk, client=mock_client, cache=cache)
    assert len(res2.entities) == 3
    assert len(res2.triplets) == 1
    assert mock_client.chat_json.call_count == 2  # Không tăng số lần gọi mock
    assert res2.cache_hit is True
    assert res2.to_dict()["cache_hit"] is True


def test_extract_chunk_prompt_version_change(tmp_path, mock_client, sample_chunk):
    """Đổi prompt_version -> cache miss, gọi lại client.chat_json."""
    cache = DiskCache(tmp_path / "cache")

    extract_chunk(sample_chunk, client=mock_client, cache=cache, prompt_version="v2")
    assert mock_client.chat_json.call_count == 2

    # Đổi sang v3 -> miss cache -> gọi lại thêm 2 lần
    extract_chunk(sample_chunk, client=mock_client, cache=cache, prompt_version="v3")
    assert mock_client.chat_json.call_count == 4


def test_pass2_receives_exact_entities_from_pass1(tmp_path, sample_chunk):
    """Pass 2 chỉ nhận entities từ Pass 1, không tự bịa thêm entity ngoài danh sách."""
    cache = DiskCache(tmp_path / "cache")
    captured_pass2_messages = []

    client = MagicMock()
    client.chat_model = "test-model"

    def _chat_json_side_effect(messages, schema):
        if schema is EntityOutput:
            return EntityOutput(
                entities=[
                    Entity(name="Trần Hưng Đạo", type="Person"),
                    Entity(name="Đại Việt", type="Polity"),
                ]
            )
        elif schema is RelationOutput:
            captured_pass2_messages.extend(messages)
            return RelationOutput(triplets=[])
        raise ValueError(f"Unknown schema: {schema}")

    client.chat_json.side_effect = _chat_json_side_effect

    extract_chunk(sample_chunk, client=client, cache=cache)

    assert len(captured_pass2_messages) > 0
    last_user_content = captured_pass2_messages[-1]["content"]

    # Đảm bảo danh sách thực thể từ Pass 1 được đưa chính xác vào prompt Pass 2
    assert "Trần Hưng Đạo (Person)" in last_user_content
    assert "Đại Việt (Polity)" in last_user_content
    # Không chứa thực thể không có trong Pass 1
    assert "Quân Nguyên" not in last_user_content


def test_triplet_with_invalid_evidence_is_rejected(tmp_path, sample_chunk):
    """Triplet có evidence bịa (không có trong chunk) bị validator loại bỏ và ghi vào rejects.jsonl."""
    cache = DiskCache(tmp_path / "cache")
    reject_file = tmp_path / "rejects.jsonl"

    client = MagicMock()
    client.chat_model = "test-model"

    def _chat_json_side_effect(messages, schema):
        if schema is EntityOutput:
            return EntityOutput(entities=[Entity(name="Lý Thường Kiệt", type="Person")])
        elif schema is RelationOutput:
            return RelationOutput(
                triplets=[
                    Triplet(
                        head="Lý Thường Kiệt",
                        relation="COMMANDED",
                        tail="Trận Như Nguyệt",
                        # Evidence giả hoàn toàn không xuất hiện trong sample_chunk text
                        evidence="Một câu bịa đặt hoàn toàn về chiến dịch tương lai",
                        confidence=0.9,
                    )
                ]
            )

    client.chat_json.side_effect = _chat_json_side_effect

    res = extract_chunk(
        sample_chunk,
        client=client,
        cache=cache,
        record_rejects=True,
        reject_path=reject_file,
    )

    # Triplet bị loại khỏi output chính
    assert len(res.triplets) == 0
    assert len(res.rejects) == 1
    assert "evidence_not_in_chunk" in res.rejects[0]["reasons"]

    # File rejects.jsonl được ghi nhận
    assert reject_file.exists()
    reject_content = reject_file.read_text(encoding="utf-8")
    assert "evidence_not_in_chunk" in reject_content


def test_chunk_failure_does_not_abort_job(tmp_path):
    """Một chunk gặp lỗi (mạng, timeout, parse) không làm dừng cả job; ghi vào failed_chunks.jsonl."""
    chunks = [
        {"id": "chunk-1", "text": "Trần Quốc Tuấn chỉ huy quân Đại Việt.", "period_id": "tran"},
        {"id": "chunk-bad", "text": "Đoạn văn gây crash mô hình.", "period_id": "tran"},
        {"id": "chunk-3", "text": "Ngô Quyền chiến thắng quân Nam Hán.", "period_id": "bacthuoc"},
    ]
    chunks_file = tmp_path / "chunks.jsonl"
    with open(chunks_file, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    client = MagicMock()
    client.chat_model = "test-model"

    def _side_effect(messages, schema):
        # Nếu là chunk-bad thì ném lỗi TimeoutError
        content_str = " ".join(m.get("content", "") for m in messages)
        if "gây crash" in content_str:
            raise TimeoutError("Ollama server timeout sau 3 lần retry")
        if schema is EntityOutput:
            return EntityOutput(entities=[Entity(name="Nhân vật", type="Person")])
        return RelationOutput(triplets=[])

    client.chat_json.side_effect = _side_effect

    out_dir = tmp_path / "extracted"
    summary = run(
        chunks_path=chunks_file,
        output_dir=out_dir,
        client=client,
        cache=DiskCache(tmp_path / "cache"),
    )

    assert summary["processed"] == 2
    assert summary["errors"] == 1

    # failed_chunks.jsonl ghi nhận chunk lỗi
    failed_file = out_dir / "failed_chunks.jsonl"
    assert failed_file.exists()
    failed_lines = [json.loads(line) for line in failed_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(failed_lines) == 1
    assert failed_lines[0]["chunk_id"] == "chunk-bad"
    assert "TimeoutError" in failed_lines[0]["error_type"]

    # extractions.jsonl chứa 2 chunk thành công
    ext_file = out_dir / "extractions.jsonl"
    assert ext_file.exists()
    ext_lines = [json.loads(line) for line in ext_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(ext_lines) == 2
    cids = [r["chunk_id"] for r in ext_lines]
    assert "chunk-1" in cids
    assert "chunk-3" in cids


def test_resume_skips_existing_chunks(tmp_path, mock_client):
    """Output đã có chunk A -> chạy lại với input gồm A và B thì chỉ xử lý mới B."""
    out_dir = tmp_path / "extracted"
    out_dir.mkdir(parents=True, exist_ok=True)
    ext_file = out_dir / "extractions.jsonl"

    # Giả lập chunk A đã được xử lý trước đó trong extractions.jsonl
    with open(ext_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"chunk_id": "chunk-A", "entities": [], "triplets": []}) + "\n")

    chunks = [
        {"id": "chunk-A", "text": "Nội dung A", "period_id": "tran"},
        {"id": "chunk-B", "text": "Nội dung B", "period_id": "tran"},
    ]
    chunks_file = tmp_path / "chunks.jsonl"
    with open(chunks_file, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    summary = run(
        chunks_path=chunks_file,
        output_dir=out_dir,
        client=mock_client,
        cache=DiskCache(tmp_path / "cache"),
    )

    # Chunk A bị bỏ qua qua resume, chỉ Chunk B được xử lý mới
    assert summary["skipped_resume"] == 1
    assert summary["processed"] == 1
    assert mock_client.chat_json.call_count == 2  # Chỉ gọi cho chunk B (Pass 1 + Pass 2)

    # File extractions.jsonl có đủ cả 2 chunk
    ext_lines = [json.loads(line) for line in ext_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(ext_lines) == 2
    assert ext_lines[0]["chunk_id"] == "chunk-A"
    assert ext_lines[1]["chunk_id"] == "chunk-B"


def test_era_filtering_by_period_membership(tmp_path, mock_client):
    """--era lọc đúng theo period_id thuộc era (dựa trên cấu hình periods.yaml)."""
    # Dùng các period thật từ periods.yaml:
    # "tran" thuộc era "phongkien", "dongson" thuộc era "tiensu"
    chunks = [
        {"id": "chunk-tran", "text": "Nội dung nhà Trần", "period_id": "tran"},
        {"id": "chunk-dongson", "text": "Nội dung Văn hóa Đông Sơn", "period_id": "dongson"},
    ]
    chunks_file = tmp_path / "chunks.jsonl"
    with open(chunks_file, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    out_dir = tmp_path / "extracted"
    summary = run(
        era="phongkien",
        chunks_path=chunks_file,
        output_dir=out_dir,
        client=mock_client,
        cache=DiskCache(tmp_path / "cache"),
    )

    # Chỉ chunk-tran thuộc era phongkien được xử lý
    assert summary["processed"] == 1
    ext_file = out_dir / "extractions.jsonl"
    ext_lines = [json.loads(line) for line in ext_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(ext_lines) == 1
    assert ext_lines[0]["chunk_id"] == "chunk-tran"


def test_tier_s_structured_mode_runs_without_llm(tmp_path):
    """Tier S (--structured) chạy độc lập tạo structured.jsonl và tuyệt đối không gọi LLM."""
    client = MagicMock()
    # Nếu client bị gọi trong chế độ structured thì sẽ fail test
    client.chat_json.side_effect = AssertionError("LLM chat_json không được phép gọi khi chạy --structured!")

    out_dir = tmp_path / "extracted"
    summary = run(
        structured=True,
        client=client,
        output_dir=out_dir,
    )

    # Không gọi LLM
    assert client.chat_json.call_count == 0
    assert summary["processed"] == 0

    # File structured.jsonl được tạo ra và chứa các triplet backbone
    struct_file = out_dir / "structured.jsonl"
    assert struct_file.exists()
    rows = [json.loads(line) for line in struct_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) > 0
    # Nguồn gốc là backbone
    assert any(r.get("source") == "backbone" for r in rows)


def test_extract_result_dataclass_contract_and_backward_compatibility():
    """Kiểm tra ExtractResult dataclass: truy cập thuộc tính, serialize to_dict/to_json_dict, và đọc tương thích từ dòng JSON cũ."""
    res = ExtractResult(
        chunk_id="42-000",
        entities=[{"name": "Trần Hưng Đạo", "type": "Person"}],
        triplets=[{"head": "Trần Hưng Đạo", "relation": "COMMANDED", "tail": "Trận Bạch Đằng"}],
        rejects=[{"triplet": {}, "reasons": ["invalid_head"]}],
        cache_hit=True,
    )
    # 1. Truy cập thuộc tính
    assert res.chunk_id == "42-000"
    assert len(res.entities) == 1
    assert len(res.triplets) == 1
    assert len(res.rejects) == 1
    assert res.cache_hit is True

    # 2. Không hỗ trợ lặp ngầm (unpack tuple)
    with pytest.raises(TypeError):
        _ = iter(res)

    # 3. Serialization to_dict() và to_json_dict()
    d = res.to_dict()
    assert d == to_json_dict(res)
    assert set(d.keys()) == {"chunk_id", "entities", "triplets", "rejects", "cache_hit"}
    serialized = json.dumps(d, ensure_ascii=False)
    deserialized = json.loads(serialized)
    assert deserialized == d

    # 4. Tương thích ngược: Đọc dòng JSON từ file extractions.jsonl định dạng cũ
    old_json_line = (
        '{"chunk_id": "42-000", "entities": [{"name": "Trần Hưng Đạo", "type": "Person"}], '
        '"triplets": [{"head": "Trần Hưng Đạo", "relation": "COMMANDED", "tail": "Trận Bạch Đằng"}], '
        '"rejects": [], "cache_hit": false}'
    )
    parsed_old = json.loads(old_json_line)
    res_from_old = ExtractResult(**parsed_old)
    assert res_from_old.chunk_id == "42-000"
    assert res_from_old.entities == [{"name": "Trần Hưng Đạo", "type": "Person"}]
    assert res_from_old.cache_hit is False
    assert res_from_old.to_dict() == parsed_old
