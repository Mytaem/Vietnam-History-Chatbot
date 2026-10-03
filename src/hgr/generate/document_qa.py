"""Hỏi đáp trên tài liệu do người dùng tải lên: cắt đoạn, nhúng, lấy đoạn liên quan, trả lời có trích dẫn [D n]. (M7)"""
from __future__ import annotations

from collections.abc import Iterator

import numpy as np

CHUNK_CHARS = 700
OVERLAP = 120
TOP_K = 5

DOC_SYSTEM_PROMPT = """Bạn trả lời câu hỏi về MỘT TÀI LIỆU do người dùng cung cấp. Chỉ dùng nội dung các đoạn trong mục ĐOẠN TÀI LIỆU.
- Mỗi ý phải kèm trích dẫn [D n] đúng với đoạn đã dùng. Không bịa trích dẫn.
- Nếu các đoạn không chứa câu trả lời, nói rõ: "Tài liệu chưa đề cập nội dung này."
- Trả lời tiếng Việt, ngắn gọn, có cấu trúc."""


def split_chunks(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(". ", start + size // 2, end)
            if cut != -1:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def top_passages(question: str, passages: list[str], client, k: int = TOP_K) -> list[tuple[int, str, float]]:
    """→ [(số thứ tự đoạn gốc từ 1, nội dung, điểm tương đồng)], giảm dần theo điểm."""
    if not passages:
        return []
    vectors = np.array(client.embed([question] + passages), dtype=float)
    q, docs = vectors[0], vectors[1:]
    denom = np.linalg.norm(docs, axis=1) * (np.linalg.norm(q) or 1.0) + 1e-12
    scores = docs @ q / denom
    order = np.argsort(-scores)[:k]
    return [(int(i) + 1, passages[int(i)], float(scores[i])) for i in order]


def build_context(hits: list[tuple[int, str, float]]) -> str:
    return "\n\n".join(f"[D{n}] {text}" for n, text, _ in hits)


def answer(question: str, hits: list[tuple[int, str, float]], client, history: list[dict] | None = None) -> Iterator[str]:
    messages = [
        {"role": "system", "content": DOC_SYSTEM_PROMPT},
        *[m for m in (history or []) if m.get("role") in ("user", "assistant")][-6:],
        {"role": "user", "content": f"ĐOẠN TÀI LIỆU:\n{build_context(hits)}\n\nCÂU HỎI: {question}"},
    ]
    yield from client.chat(messages, stream=True)
