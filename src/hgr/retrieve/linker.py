"""Mention → top-k Entity (fulltext alias + vector, RRF, ưu tiên period). (M6)"""
from __future__ import annotations

from hgr.retrieve.fusion import rrf


def _fulltext(store, mention: str, limit: int) -> list[dict]:
    query = mention.replace('"', " ").strip()
    if not query:
        return []
    rows = store.run(
        "CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score "
        "RETURN node.id AS id, score ORDER BY score DESC LIMIT $limit",
        q=f'"{query}"~', limit=limit,
    )
    return [{"id": r["id"]} for r in rows]


def _vector(store, client, mention: str, limit: int) -> list[dict]:
    vector = client.embed([mention])[0]
    rows = store.run(
        "CALL db.index.vector.queryNodes('entity_vec', $limit, $vector) YIELD node, score "
        "RETURN node.id AS id, score ORDER BY score DESC",
        vector=vector, limit=limit,
    )
    return [{"id": r["id"]} for r in rows]


def link_mention(mention: str, store, client, prefer_periods: list[str] | None = None, k: int = 2) -> list[str]:
    """Một mention → tối đa k id Entity, ưu tiên entity thuộc `prefer_periods` khi hòa điểm."""
    fulltext_hits = _fulltext(store, mention, limit=10)
    try:
        vector_hits = _vector(store, client, mention, limit=10)
    except Exception:
        vector_hits = []
    fused = rrf([fulltext_hits, vector_hits], weights=[1.0, 1.0], k=60)
    if not fused:
        return []
    if prefer_periods:
        ids = [row["id"] for row in fused]
        in_period = set(
            r["id"] for r in store.run(
                "MATCH (e:Entity)-[:IN_PERIOD]->(p:Period) WHERE e.id IN $ids AND p.id IN $periods "
                "RETURN DISTINCT e.id AS id",
                ids=ids, periods=prefer_periods,
            )
        )
        fused.sort(key=lambda row: row["id"] not in in_period)
    return [row["id"] for row in fused[:k]]


def link_all(mentions: list[str], store, client, prefer_periods: list[str] | None = None, k: int = 2) -> list[str]:
    """Gộp id Entity tìm được cho mọi mention, giữ thứ tự xuất hiện, không trùng."""
    seen: list[str] = []
    for mention in mentions:
        for entity_id in link_mention(mention, store, client, prefer_periods, k):
            if entity_id not in seen:
                seen.append(entity_id)
    return seen
