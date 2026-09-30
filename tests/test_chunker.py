"""Test process/chunker.py"""
from hgr.process.chunker import chunk_article, is_post_cutoff, split_sentences
from hgr.process.parser import LEAD


def make_article(sections, period_id="tran", tier="A"):
    return {
        "page_id": 42, "title": "Trần Hưng Đạo", "label": "Trần Hưng Đạo", "qid": "Q1",
        "period_id": period_id, "period_ids": [period_id], "tier": tier,
        "sections": [{"path": p, "text": t} for p, t in sections],
        "links": [{"surface": "Nguyên Mông", "target": "Đế quốc Mông Cổ", "section": "Sự nghiệp", "offset": 0}],
    }


def test_split_sentences_keeps_abbreviations_and_initials():
    text = "TS. Nguyễn Văn A nói vậy. Ông Q. Trần sinh năm 1945. Câu cuối!"
    assert split_sentences(text) == ["TS. Nguyễn Văn A nói vậy.", "Ông Q. Trần sinh năm 1945.", "Câu cuối!"]


def test_chunks_do_not_cut_sentences_and_respect_target():
    sentence = "Năm 1288 Trần Hưng Đạo đánh tan quân Nguyên Mông trên sông Bạch Đằng lần thứ ba."
    article = make_article([(LEAD, "Mở đầu ngắn."), ("Sự nghiệp", " ".join([sentence] * 40))])
    chunks = chunk_article(article, target_tokens=120, overlap_sentences=1, min_tokens=20)
    body = [c for c in chunks if c["section_path"] == "Sự nghiệp"]
    assert len(body) > 1
    for c in body:
        assert c["text"].endswith(".")
        assert c["tokens"] <= 120 + 30
    assert body[1]["text"].startswith(sentence)  # chồng 1 câu


def test_chunk_fields():
    article = make_article([(LEAD, "Trần Hưng Đạo (1228 – 1300) là danh tướng nhà Trần."),
                            ("Sự nghiệp", "Ông ba lần đánh bại quân Nguyên Mông vào thế kỷ XIII.")])
    chunks = chunk_article(article, min_tokens=5)
    first, second = chunks
    assert first["id"] == "42-000"
    assert first["header"] == ("[Bài: Trần Hưng Đạo | Mục: Mở đầu | Chủ thể: Trần Hưng Đạo | "
                               "Giai đoạn: Nhà Trần (1225–1400)]")
    assert (first["min_year"], first["max_year"]) == (1228, 1300)
    assert second["links"] == ["Đế quốc Mông Cổ"]
    assert (second["min_year"], second["max_year"]) == (1201, 1300)


def test_cutoff_1945_drops_body_but_keeps_lead():
    article = make_article(
        [(LEAD, "Ông mất năm 1969."), ("Về sau", "Năm 1975 đất nước thống nhất."), ("Trước đó", "Năm 1945 ông ở Hà Nội.")],
        period_id="1939_1945",
    )
    chunks = chunk_article(article, min_tokens=5)
    paths = [c["section_path"] for c in chunks]
    assert paths == [LEAD, "Trước đó"]
    assert is_post_cutoff({"min_year": 1946}) and not is_post_cutoff({"min_year": 1945})
    assert not is_post_cutoff({"min_year": None})


def test_tier_b_limited_by_max_chunks_b():
    sections = [(f"Mục {i}", f"Đoạn văn lịch sử số {i} với đủ câu để tạo chunk riêng biệt. Trần Hưng Đạo sinh năm 1228 và mất năm 1300.") for i in range(10)]
    article = make_article(sections, tier="B")
    chunks = chunk_article(article, min_tokens=5)
    # Mặc định trong settings.yaml extract.max_chunks_b = 3
    assert len(chunks) == 3
    assert [c["section_path"] for c in chunks] == ["Mục 0", "Mục 1", "Mục 2"]
    assert [c["chunk_index"] for c in chunks] == [0, 1, 2]
    for c in chunks:
        assert c["tier"] == "B"


def test_tier_a_not_limited():
    sections = [(f"Mục {i}", f"Đoạn văn lịch sử số {i} với đủ câu để tạo chunk riêng biệt. Trần Hưng Đạo sinh năm 1228 và mất năm 1300.") for i in range(10)]
    article = make_article(sections, tier="A")
    chunks = chunk_article(article, min_tokens=5)
    assert len(chunks) == 10
    assert [c["chunk_index"] for c in chunks] == list(range(10))


def test_tier_b_custom_and_dynamic_settings(monkeypatch):
    sections = [(f"Mục {i}", f"Đoạn văn lịch sử số {i} với đủ câu để tạo chunk riêng biệt. Trần Hưng Đạo sinh năm 1228 và mất năm 1300.") for i in range(10)]
    article = make_article(sections, tier="B")

    # Truyền trực tiếp max_chunks_b = 2
    chunks_2 = chunk_article(article, min_tokens=5, max_chunks_b=2)
    assert len(chunks_2) == 2
    assert [c["chunk_index"] for c in chunks_2] == [0, 1]

    # Monkeypatch settings
    from hgr import config
    real_settings = config.get_settings()
    mock_settings = config.Settings(dict(real_settings))
    mock_extract = dict(mock_settings.get("extract", {}))
    mock_extract["max_chunks_b"] = 4
    mock_settings["extract"] = mock_extract

    monkeypatch.setattr(config, "get_settings", lambda *args, **kwargs: mock_settings)
    chunks_4 = chunk_article(article, min_tokens=5, max_chunks_b=None)
    assert len(chunks_4) == 4
    assert [c["chunk_index"] for c in chunks_4] == [0, 1, 2, 3]


def test_extractor_tier_b_on_chunked_data(tmp_path):
    import json
    from hgr.extract.extractor import run
    from unittest.mock import MagicMock

    # Tạo chunks.jsonl có cả chunk Tier A và Tier B (đã áp dụng chunk_article)
    sections = [(f"Mục {i}", f"Đoạn {i}. Trần Hưng Đạo sinh năm 1228.") for i in range(10)]
    art_a = make_article(sections, tier="A")
    art_a["page_id"] = 101
    art_b = make_article(sections, tier="B")
    art_b["page_id"] = 102

    chunks_a = chunk_article(art_a, min_tokens=5)
    chunks_b = chunk_article(art_b, min_tokens=5, max_chunks_b=3)
    assert len(chunks_a) == 10
    assert len(chunks_b) == 3

    chunks_file = tmp_path / "chunks.jsonl"
    with open(chunks_file, "w", encoding="utf-8") as f:
        for c in chunks_a + chunks_b:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Mock OllamaClient trả về entities/triplets rỗng
    mock_client = MagicMock()
    mock_client.chat_json.return_value = {"entities": [], "triplets": []}

    out_dir = tmp_path / "extracted"
    stats = run(
        chunks_path=str(chunks_file),
        tier="B",
        output_dir=str(out_dir),
        client=mock_client,
    )
    # Số chunk xử lý đúng bằng 3 chunk của Tier B
    assert stats["processed"] == 3


