"""Chunk theo section → câu (~500 token), header ngữ cảnh, years[], cutoff 1945. (M3)"""
from __future__ import annotations


def chunk_article(article: dict, target_tokens: int = 500, overlap_sentences: int = 1) -> list[dict]:
    """→ [{id, page_title, section_path, header, text, links[], years[], min_year, max_year,
          period_id, tier}]"""
    raise NotImplementedError


def is_post_cutoff(chunk: dict, max_year: int = 1945) -> bool:
    raise NotImplementedError
