"""Test generate/context_builder.py."""
from hgr.generate.context_builder import build_context
from hgr.retrieve.pipeline import RetrievalResult


def _result(**overrides):
    defaults = dict(plan=None, top_chunks=[], triplets=[], paths=[], subgraph={}, out_of_scope=False)
    defaults.update(overrides)
    return RetrievalResult(**defaults)


def test_source_quote_is_not_truncated_to_300_chars():
    """Cắt cứng 300 ký tự từng chặt ngang câu ngay trước chi tiết quan trọng (vd "...thuộc địa phận
    [Hải Dương]" mất [Hải Dương]), khiến model tự đoán bừa chỗ bị thiếu. Ngân sách token đã áp đúng lúc
    chọn chunk (max_tokens), nên NGUỒN phải giữ nguyên văn phần đã chọn, không cắt thêm theo ký tự."""
    long_text = "Đền Kiếp Bạc nơi thờ phụng ông thuộc địa phận " + "x" * 280 + " tỉnh Hải Dương."
    result = _result(top_chunks=[{"id": "c1", "text": long_text, "page_title": "T", "section_path": "S"}])
    context, citations = build_context(result)
    assert "tỉnh Hải Dương" in context
    assert citations[0]["quote"] == long_text


def test_entities_relations_and_scope_rendered():
    plan = type("P", (), {"periods": []})()
    subgraph = {
        "nodes": [{"id": "a", "name": "A", "type": "Person", "start_year": 1228, "end_year": 1300}],
        "edges": [{"source_id": "a", "target_id": "b", "type": "CHILD_OF", "role": None, "start_year": 1228,
                   "evidence_chunk_ids": []}],
    }
    result = _result(plan=plan, subgraph=subgraph, triplets=subgraph["edges"])
    context, _ = build_context(result)
    assert "### PHẠM VI" in context
    assert "Toàn bộ phạm vi dữ liệu" in context
    assert "A (1228–1300) — Person" in context
    assert "A —CHILD_OF(1228)→ b" in context


def test_no_sources_no_section():
    context, citations = build_context(_result())
    assert "### NGUỒN" not in context
    assert citations == []
