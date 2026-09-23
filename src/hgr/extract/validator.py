"""Kiểm định: domain→range, evidence ⊂ chunk, năm hợp lệ, cutoff 1945, confidence. (M4)"""
from __future__ import annotations


def validate_triplet(triplet: dict, entities: dict[str, dict], chunk_text: str,
                     ontology: dict, max_year: int = 1945) -> str | None:
    """→ None nếu hợp lệ, ngược lại là lý do loại."""
    raise NotImplementedError
