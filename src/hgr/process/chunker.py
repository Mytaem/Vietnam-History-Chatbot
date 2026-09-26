"""Chunk theo section → câu (~500 token), header ngữ cảnh, years[], cutoff 1945. (M3)"""
from __future__ import annotations

import math
import re

from hgr.periods import all_periods
from hgr.process.normalize import parse_time
from hgr.process.parser import LEAD

_ABBREVIATIONS = {"ts", "gs", "pgs", "ths", "th.s", "bs", "ks", "tr", "st", "mr", "mrs", "dr", "tp", "v.v",
                  "vv", "nxb", "sđd", "tt", "q", "p", "ctv", "cn", "vs"}
_BOUNDARY = re.compile(r"[.!?…]+[\"”’»)\]]*(?=\s)")
_SENTENCE_START = re.compile(r"\s+([\"“‘«(\[]?[^\W_])")


def estimate_tokens(text: str) -> int:
    # Tokenizer Qwen tách âm tiết tiếng Việt có dấu thành ~1.4 token/âm tiết.
    return math.ceil(len(text.split()) * 1.4)


def split_sentences(text: str) -> list[str]:
    """Tách câu bằng dấu câu + chữ hoa/số đầu câu, tránh cắt sau viết tắt và chữ cái đầu tên."""
    sentences: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        start = 0
        for m in _BOUNDARY.finditer(paragraph):
            nxt = _SENTENCE_START.match(paragraph, m.end())
            if not nxt:
                continue
            first = nxt.group(1)[-1]
            if not (first.isupper() or first.isdigit()):
                continue
            words = paragraph[start:m.start() + 1].split()
            last = words[-1].rstrip(".!?…").lower() if words else ""
            if last in _ABBREVIATIONS or (len(last) == 1 and last.isalpha()):
                continue
            sentences.append(paragraph[start:m.end()].strip())
            start = m.end()
        tail = paragraph[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def _pack(sentences: list[str], target_tokens: int, overlap: int, min_tokens: int) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    fresh = 0
    for sentence in sentences:
        tokens = estimate_tokens(sentence)
        if current and fresh and sum(map(estimate_tokens, current)) + tokens > target_tokens:
            groups.append(current)
            current = current[-overlap:] if overlap else []
            if sum(map(estimate_tokens, current)) + tokens > target_tokens:
                current = []
            fresh = 0
        current.append(sentence)
        fresh += 1
    if current:
        new_part = current[-fresh:]
        if groups and sum(map(estimate_tokens, new_part)) < min_tokens:
            groups[-1].extend(new_part)
        else:
            groups.append(current)
    return groups


def _top(path: str) -> str:
    return path.split(" > ", 1)[0]


def _fmt_year(y: int) -> str:
    return f"{-y} TCN" if y < 0 else str(y)


def chunk_article(
    article: dict,
    target_tokens: int = 500,
    overlap_sentences: int = 1,
    min_tokens: int = 80,
    max_year: int = 1945,
    drop_post_cutoff: bool = True,
) -> list[dict]:
    """→ [{id, page_title, section_path, header, text, links[], years[], min_year, max_year,
          period_id, tier}]"""
    period = next((p for p in all_periods() if p.id == article.get("period_id")), None)
    hint = (period.start, period.end) if period else None
    period_label = f"{period.name} ({_fmt_year(period.start)}–{_fmt_year(period.end)})" if period else "?"

    pieces: list[dict] = []
    for section in article.get("sections", []):
        sentences = split_sentences(section["text"])
        for group in _pack(sentences, target_tokens, overlap_sentences, min_tokens):
            text = " ".join(group)
            tokens = estimate_tokens(text)
            prev = pieces[-1] if pieces else None
            if (
                prev is not None
                and _top(prev["path"]) == _top(section["path"])
                and prev["tokens"] + tokens <= target_tokens
            ):
                prev["text"] += "\n" + text
                prev["tokens"] += tokens
                prev["sections"].append(section["path"])
                if prev["path"] != section["path"]:
                    prev["path"] = _top(section["path"])
                continue
            pieces.append({"path": section["path"], "text": text, "tokens": tokens, "sections": [section["path"]]})

    links_by_section: dict[str, list[dict]] = {}
    for link in article.get("links", []):
        links_by_section.setdefault(link["section"], []).append(link)

    subject = article.get("label") or article["title"]
    chunks = []
    for index, piece in enumerate(pieces):
        spans = parse_time(piece["text"], hint)
        years = sorted({y for s in spans for y in (s.start, s.end)})
        candidates = [link for path in piece["sections"] for link in links_by_section.get(path, [])]
        links = list(dict.fromkeys(link["target"] for link in candidates if link["surface"] in piece["text"]))
        chunk = {
            "id": f"{article['page_id']}-{index:03d}",
            "page_id": article["page_id"],
            "page_title": article["title"],
            "qid": article.get("qid"),
            "chunk_index": index,
            "section_path": piece["path"],
            "header": f"[Bài: {article['title']} | Mục: {piece['path']} | Chủ thể: {subject} | Giai đoạn: {period_label}]",
            "text": piece["text"],
            "tokens": piece["tokens"],
            "links": links,
            "years": years,
            "min_year": min((s.start for s in spans), default=None),
            "max_year": max((s.end for s in spans), default=None),
            "legendary": any(s.legendary for s in spans),
            "period_id": article.get("period_id"),
            "period_ids": article.get("period_ids", []),
            "tier": article.get("tier"),
        }
        if drop_post_cutoff and piece["path"] != LEAD and is_post_cutoff(chunk, max_year):
            continue
        chunks.append(chunk)
    return chunks


def is_post_cutoff(chunk: dict, max_year: int = 1945) -> bool:
    """Chunk có năm và mọi năm đều sau mốc cắt."""
    return chunk.get("min_year") is not None and chunk["min_year"] > max_year
