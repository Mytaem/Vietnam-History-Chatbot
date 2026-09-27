"""Kiểm định: domain→range, evidence ⊂ chunk, năm hợp lệ, cutoff 1945, confidence. (M4)"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

DEFAULT_ONTOLOGY = {
    "relations": {
        "RULED": {"domain": ["Person"], "range": ["Polity"]},
        "RULED_OVER": {"domain": ["Person", "Polity"], "range": ["Place", "Polity"]},
        "CAPITAL_OF": {"domain": ["Place"], "range": ["Polity"]},
        "CHILD_OF": {"domain": ["Person"], "range": ["Person"]},
        "SPOUSE_OF": {"domain": ["Person"], "range": ["Person"]},
        "PARTICIPATED_IN": {"domain": ["Person", "Polity", "Organization"], "range": ["Event"]},
        "RELATED_TO": {"domain": ["*"], "range": ["*"]},
    }
}


def _norm(v: str) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def _guess_type(name: str, entities: dict | None = None, fallback: str = "Unknown") -> str:
    entities = entities or {}
    key = _norm(name)
    if key in {""}:
        return fallback
    for k, val in entities.items():
        if isinstance(val, dict) and _norm(k) == key:
            t = val.get("type") or val.get("kind")
            if t:
                return str(t)
    if any(token in key for token in ("vua", "hoàng", "thánh", "tướng", "thiền", "giáo", "nhà cách mạng", "nữ vương", "quốc vương")):
        return "Person"
    if any(token in key for token in ("thành", "sông", "núi", "động", "hà nội", "hải phòng", "huế", "đà nẵng", "kinh đô", "địa danh", "đô thị", "nơi sinh", "nơi mất")):
        return "Place"
    if any(token in key for token in ("triều", "nhà", "quốc gia", "vương quốc", "nước", "đế quốc", "văn lang", "âu lạc", "đại việt", "đại nam")):
        return "Polity"
    if any(token in key for token in ("chiến", "trận", "khởi nghĩa", "hòa ước", "dựng nước", "cách mạng", "đại hội")):
        return "Event"
    return fallback


def validate_triplet(triplet: dict, entities: dict | str, chunk_text: str | None = None,
                     ontology: dict | None = None, max_year: int = 1945) -> dict:
    """→ {'ok': bool, 'reasons': [..]}.

    Hỗ trợ cả cú pháp cũ `validate_triplet(triplet, chunk_text, ...)` và cú pháp mới với entity map.
    """
    if isinstance(entities, str):
        chunk_text, entities, ontology = entities, {}, ontology or DEFAULT_ONTOLOGY
    else:
        entities = entities or {}
        if chunk_text is None:
            chunk_text = ""
        ontology = ontology or DEFAULT_ONTOLOGY

    reasons: list[str] = []
    rel = triplet.get("relation")
    rel_def = (ontology or DEFAULT_ONTOLOGY).get("relations", {}).get(rel, {})
    domain = rel_def.get("domain", ["*"])
    range_ = rel_def.get("range", ["*"])

    head = str(triplet.get("head") or "")
    tail = str(triplet.get("tail") or "")
    if not head or not tail:
        reasons.append("head/tail thiếu")
    if rel is None:
        reasons.append("relation thiếu")

    head_type = _guess_type(head, entities)
    tail_type = _guess_type(tail, entities)
    if head_type != "Unknown" and "*" not in domain and head_type not in domain:
        reasons.append(f"head type {head_type!r} không thuộc domain của {rel}")
    if tail_type != "Unknown" and "*" not in range_ and tail_type not in range_:
        reasons.append(f"tail type {tail_type!r} không thuộc range của {rel}")

    evidence = str(triplet.get("evidence") or "").strip()
    chunk = str(chunk_text or "")
    if evidence:
        evidence_norm = _norm(evidence)
        chunk_norm = _norm(chunk)
        if evidence_norm not in chunk_norm:
            sim = SequenceMatcher(None, evidence_norm, chunk_norm).ratio()
            if sim < 0.9:
                reasons.append("evidence không nằm trong chunk hoặc không khớp đủ 90%")
    if triplet.get("confidence", 1.0) is not None and float(triplet.get("confidence", 1.0)) < 0.6:
        reasons.append("confidence dưới ngưỡng 0.6")

    for key in ("start_year", "end_year"):
        val = triplet.get(key)
        if val is not None:
            try:
                year = int(val)
            except (TypeError, ValueError):
                reasons.append(f"{key} không phải số nguyên")
                continue
            if year > max_year:
                reasons.append(f"{key} vượt quá mốc cắt {max_year}")
    if triplet.get("start_year") is not None and triplet.get("end_year") is not None:
        if int(triplet["start_year"]) > int(triplet["end_year"]):
            reasons.append("start_year > end_year")

    return {"ok": not reasons, "reasons": reasons}
