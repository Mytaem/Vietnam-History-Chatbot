"""Test process/chunker.py"""
from hgr.process.chunker import chunk_article, is_post_cutoff, split_sentences
from hgr.process.parser import LEAD


def make_article(sections, period_id="tran"):
    return {
        "page_id": 42, "title": "Trần Hưng Đạo", "label": "Trần Hưng Đạo", "qid": "Q1",
        "period_id": period_id, "period_ids": [period_id], "tier": "A",
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
