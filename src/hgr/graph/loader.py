"""Nạp đồ thị: Era/Period (PART_OF, NEXT) → backbone → Article/Chunk/Entity/Relation
→ MENTIONS, IN_PERIOD, degree, display_name. (M5)"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from hgr.extract.schemas import RelType


def _read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _properties(row: dict, exclude: set[str] | None = None) -> dict:
    exclude = exclude or set()
    return {
        key: value for key, value in row.items()
        if key not in exclude
        and value is not None
        and isinstance(value, (str, int, float, bool, list))
    }

def load_periods(store, eras) -> None:
    era_rows = []
    period_rows = []
    next_era_rows = []
    next_period_rows = []
    previous_era = None
    previous_period = None
    for era in eras:
        era_rows.append({
            "id": era.id,
            "name": era.name,
            "start": era.start,
            "end": era.end,
            "color": era.color,
            "aliases": era.aliases,
            "aliases_text": " ".join([era.name, *era.aliases]),
        })
        if previous_era is not None:
            next_era_rows.append({"from": previous_era, "to": era.id})
        previous_era = era.id
        for period in era.periods:
            period_rows.append({
                "id": period.id,
                "name": period.name,
                "era_id": era.id,
                "start": period.start,
                "end": period.end,
                "parallel": period.parallel,
                "aliases": period.aliases,
                "aliases_text": " ".join([period.name, *period.aliases]),
                "legendary": period.legendary,
                "disputed": period.disputed,
            })
            if not period.parallel:
                if previous_period is not None:
                    next_period_rows.append({"from": previous_period, "to": period.id})
                previous_period = period.id
    if store is not None:
        store.run_batches("UNWIND $rows AS row MERGE (e:Era {id: row.id}) SET e += row", era_rows)
        store.run_batches("UNWIND $rows AS row MERGE (p:Period {id: row.id}) SET p += row", period_rows)
        store.run_batches(
            "UNWIND $rows AS row MATCH (p:Period {id: row.id}), (e:Era {id: row.era_id}) MERGE (p)-[:PART_OF]->(e)",
            period_rows,
        )
        store.run_batches(
            "UNWIND $rows AS row MATCH (a:Era {id: row.from}), (b:Era {id: row.to}) MERGE (a)-[:NEXT]->(b)",
            next_era_rows,
        )
        store.run_batches(
            "UNWIND $rows AS row MATCH (a:Period {id: row.from}), (b:Period {id: row.to}) MERGE (a)-[:NEXT]->(b)",
            next_period_rows,
        )


def load_backbone(store, backbone_dir: str) -> None:
    path = Path(backbone_dir) / "dia_danh.yaml"
    if store is None or not path.exists():
        return
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = []
    for place in document.get("dia_danh", []):
        aliases = list(dict.fromkeys(
            [entry["name"] for entry in place.get("names", []) if entry.get("name")]
            + [place["canonical"]]
        ))
        rows.append({
            "id": f"local:{place['id']}",
            "name": place["canonical"],
            "aliases": aliases,
            "aliases_text": " ".join(aliases),
            "type": "Place",
            "historical_names_text": json.dumps(place.get("names", []), ensure_ascii=False),
        })
    store.run_batches(
        "UNWIND $rows AS row MERGE (e:Entity {id: row.id}) SET e += row",
        rows,
    )


def load_resolved(store, resolved_dir: str) -> None:
    base = Path(resolved_dir)
    entity_rows = []
    for entity in _read_jsonl(base / "entities.jsonl") or []:
        props = _properties(entity, {"description"})
        props["aliases_text"] = " ".join(entity.get("aliases", []))
        if entity.get("description"):
            props["description"] = entity["description"]
        entity_rows.append({"id": entity["id"], "props": props})
    if store is not None:
        store.run_batches(
            "UNWIND $rows AS row MERGE (e:Entity {id: row.id}) SET e += row.props",
            entity_rows,
        )

    allowed_types = set(RelType.__args__)
    relation_rows = []
    for relation in _read_jsonl(base / "relations.jsonl") or []:
        rel_type = relation.get("relation")
        if rel_type not in allowed_types:
            rel_type = "RELATED_TO"
        props = _properties(relation, {
            "head", "head_id", "tail", "tail_id", "relation",
        })
        props["id"] = relation["id"]
        props["source"] = relation.get("source", "extraction")
        relation_rows.append({
            "head_id": relation["head_id"],
            "tail_id": relation["tail_id"],
            "type": rel_type,
            "props": props,
        })
    if store is not None:
        store.run_batches(
            "UNWIND $rows AS row MATCH (a:Entity {id: row.head_id}), (b:Entity {id: row.tail_id}) "
            "CALL apoc.merge.relationship(a, row.type, {id: row.props.id}, row.props, b) YIELD rel "
            "RETURN count(rel)",
            relation_rows,
        )


def load_articles_chunks(store, data_dir: str) -> None:
    base = Path(data_dir)
    articles = []
    for article in _read_jsonl(base / "processed" / "articles.jsonl") or []:
        props = _properties(article, {"infobox", "wikidata", "sections", "links", "categories"})
        articles.append({"page_id": article["page_id"], "props": props})
    chunks = []
    for chunk in _read_jsonl(base / "processed" / "chunks.jsonl") or []:
        props = _properties(chunk)
        chunks.append({"id": chunk["id"], "page_id": chunk["page_id"], "props": props})
    if store is None:
        return
    store.run_batches(
        "UNWIND $rows AS row MERGE (a:Article {page_id: row.page_id}) SET a += row.props",
        articles,
    )
    store.run_batches(
        "UNWIND $rows AS row MERGE (c:Chunk {id: row.id}) SET c += row.props",
        chunks,
    )
    store.run_batches(
        "UNWIND $rows AS row MATCH (a:Article {page_id: row.page_id}), (c:Chunk {id: row.id}) "
        "MERGE (a)-[:HAS_CHUNK]->(c)",
        [{"page_id": row["page_id"], "id": row["id"]} for row in chunks],
    )
    mentions = [
        {"id": row["id"], "name": name}
        for row in chunks
        for name in row["props"].get("links", [])
    ]
    store.run_batches(
        "UNWIND $rows AS row MATCH (c:Chunk {id: row.id}), (e:Entity) "
        "WHERE e.name = row.name OR row.name IN coalesce(e.aliases, []) "
        "MERGE (e)-[:MENTIONS]->(c)",
        mentions,
    )
    store.run(
        "MATCH (a:Article) WHERE a.qid IS NOT NULL MATCH (e:Entity) "
        "WHERE e.id = 'qid:' + a.qid MERGE (a)-[:ABOUT]->(e)"
    )


def link_periods(store) -> None:
    """Tạo (:Entity)-[:IN_PERIOD]->(:Period) theo overlap năm."""
    if store is not None:
        store.run(
            "MATCH (c:Chunk) UNWIND coalesce(c.period_ids, [c.period_id]) AS period_id "
            "MATCH (p:Period {id: period_id}) MERGE (c)-[:IN_PERIOD]->(p)"
        )
        store.run(
            "MATCH (a:Article) WHERE a.period_id IS NOT NULL MATCH (p:Period {id: a.period_id}) "
            "MERGE (a)-[:IN_PERIOD]->(p)"
        )
        store.run(
            "MATCH (e:Entity) UNWIND coalesce(e.period_ids, []) AS period_id "
            "MATCH (p:Period {id: period_id}) MERGE (e)-[:IN_PERIOD]->(p)"
        )


def compute_degree_and_display_names(store) -> None:
    if store is not None:
        store.run(
            "MATCH (e:Entity) OPTIONAL MATCH (e)-[r]-() WITH e, count(DISTINCT r) AS degree "
            "SET e.degree = degree, e.display_name = coalesce(e.name, e.id)"
        )
