"""RRF có trọng số theo intent, boost chunk là evidence của cạnh, rerank (tùy chọn). (M6)"""
from __future__ import annotations

from hgr.log import get_logger

log = get_logger(__name__)


def rrf(ranked_lists: list[list[dict]], weights: list[float], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion có trọng số. Mỗi item là dict có khóa 'id'; item đầu gặp được giữ lại (merge theo id)."""
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}
    for ranked, weight in zip(ranked_lists, weights):
        if not weight:
            continue
        for rank, item in enumerate(ranked, start=1):
            key = item["id"]
            scores[key] = scores.get(key, 0.0) + weight / (k + rank)
            items.setdefault(key, item)
    ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [{**items[key], "rrf_score": scores[key]} for key in ordered]


def boost_evidence(items: list[dict], evidence_ids: set[str], factor: float = 1.3) -> list[dict]:
    """Nhân điểm cho chunk nằm trong evidence_ids (bằng chứng của cạnh đồ thị), rồi xếp lại."""
    boosted = []
    for item in items:
        score = item.get("rrf_score", 0.0)
        if item["id"] in evidence_ids:
            score *= factor
        boosted.append({**item, "rrf_score": score})
    boosted.sort(key=lambda item: item["rrf_score"], reverse=True)
    return boosted


_cross_encoder = None


def rerank(question: str, items: list[dict], model: str = "BAAI/bge-reranker-v2-m3") -> list[dict]:
    """Rerank bằng cross-encoder CPU (sentence-transformers, requirements-rerank.txt). Trả nguyên `items` nếu thiếu thư viện."""
    global _cross_encoder
    if not items:
        return items
    try:
        if _cross_encoder is None:
            from sentence_transformers import CrossEncoder

            _cross_encoder = CrossEncoder(model)
        scores = _cross_encoder.predict([(question, item.get("text", "")) for item in items])
        ranked = sorted(zip(items, scores), key=lambda pair: pair[1], reverse=True)
        return [{**item, "rerank_score": float(score)} for item, score in ranked]
    except Exception as e:
        log.warning("Bỏ qua rerank (thiếu sentence-transformers hoặc lỗi model): %s", e)
        return items
