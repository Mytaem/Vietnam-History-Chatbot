"""Vector + fulltext trên Chunk, lọc năm/period, gộp RRF. (M6)"""
from __future__ import annotations

from hgr.retrieve.fusion import rrf


def _year_filter(years: tuple[int, int] | None) -> tuple[str, dict]:
    if not years:
        return "", {}
    # Overlap: start <= y1 AND end >= y0. Chunk không có năm vẫn được giữ (không đủ dữ liệu để loại).
    return (
        " AND (c.min_year IS NULL OR (c.min_year <= $y1 AND coalesce(c.max_year, c.min_year) >= $y0))",
        {"y0": years[0], "y1": years[1]},
    )


def _period_filter(periods: list[str] | None) -> tuple[str, dict]:
    if not periods:
        return "", {}
    return (
        " AND (c.period_id IN $periods OR any(p IN coalesce(c.period_ids, []) WHERE p IN $periods))",
        {"periods": periods},
    )


def _fulltext(store, query: str, k: int, years, periods) -> list[dict]:
    year_clause, year_params = _year_filter(years)
    period_clause, period_params = _period_filter(periods)
    rows = store.run(
        "CALL db.index.fulltext.queryNodes('chunk_text', $q) YIELD node AS c, score "
        f"WHERE true {year_clause}{period_clause} "
        "RETURN c.id AS id, c.text AS text, c.header AS header, c.page_title AS page_title, "
        "c.section_path AS section_path, c.min_year AS min_year, c.max_year AS max_year, "
        "c.legendary AS legendary, score ORDER BY score DESC LIMIT $k",
        q=query, k=k, **year_params, **period_params,
    )
    return [dict(r) for r in rows]


def _vector(store, client, query: str, k: int, years, periods) -> list[dict]:
    vector = client.embed([query])[0]
    year_clause, year_params = _year_filter(years)
    period_clause, period_params = _period_filter(periods)
    rows = store.run(
        "CALL db.index.vector.queryNodes('chunk_vec', $k0, $vector) YIELD node AS c, score "
        f"WHERE true {year_clause}{period_clause} "
        "RETURN c.id AS id, c.text AS text, c.header AS header, c.page_title AS page_title, "
        "c.section_path AS section_path, c.min_year AS min_year, c.max_year AS max_year, "
        "c.legendary AS legendary, score ORDER BY score DESC LIMIT $k",
        # Lọc sau khi lấy top-N rộng hơn k, vì lọc năm/giai đoạn làm trong WHERE sau ANN.
        vector=vector, k0=max(k * 4, 40), k=k, **year_params, **period_params,
    )
    return [dict(r) for r in rows]


def search(query: str, store, client, k: int = 20, years: tuple[int, int] | None = None,
           periods: list[str] | None = None) -> list[dict]:
    fulltext_hits = _fulltext(store, query, k, years, periods)
    try:
        vector_hits = _vector(store, client, query, k, years, periods)
    except Exception:
        vector_hits = []
    return rrf([vector_hits, fulltext_hits], weights=[1.0, 1.0], k=60)[:k]
