"""Nạp đồ thị: Era/Period (PART_OF, NEXT) → backbone → Article/Chunk/Entity/Relation
→ MENTIONS, IN_PERIOD, degree, display_name. (M5)"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from hgr.extract.schemas import RelType
from hgr.log import get_logger

log = get_logger(__name__)


def check_apoc(store) -> str:
    """Kiểm tra APOC đã sẵn sàng chưa, trả về version (ví dụ: '5.26.0')."""
    if store is None:
        return ""
    try:
        records = store.run("RETURN apoc.version() AS version")
        if records and records[0].get("version"):
            return str(records[0]["version"])
    except Exception as e:
        log.error("Lỗi khi kiểm tra APOC: %s", e)
    raise RuntimeError("APOC không sẵn sàng trên Neo4j instance!")


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
        "UNWIND $rows AS row MERGE (e:Entity {id: row.id}) SET e += row "
        "WITH e "
        "CALL apoc.create.addLabels(e, ['Place']) YIELD node "
        "RETURN count(node)",
        rows,
    )


def load_resolved(store, resolved_dir: str, rejects_path: str | Path | None = None) -> None:
    base = Path(resolved_dir)
    entity_rows = []
    for entity in _read_jsonl(base / "entities.jsonl") or []:
        props = _properties(entity, {"description"})
        props["aliases_text"] = " ".join(entity.get("aliases", []))
        if entity.get("description"):
            props["description"] = entity["description"]
        ent_type = entity.get("type") or props.get("type")
        entity_rows.append({
            "id": entity["id"],
            "type": ent_type if ent_type and ent_type != "Unknown" else None,
            "props": props,
        })
    if store is not None:
        store.run_batches(
            "UNWIND $rows AS row MERGE (e:Entity {id: row.id}) SET e += row.props "
            "WITH e, row "
            "WHERE row.type IS NOT NULL AND row.type <> '' "
            "CALL apoc.create.addLabels(e, [row.type]) YIELD node "
            "RETURN count(node)",
            entity_rows,
        )

    allowed_types = set(RelType.__args__)
    relation_rows = []
    rejected_rows = []
    for relation in _read_jsonl(base / "relations.jsonl") or []:
        rel_type = relation.get("relation")
        if rel_type not in allowed_types:
            log.warning(
                "Bỏ qua quan hệ không hợp lệ trong ontology: '%s' (head=%s, tail=%s)",
                rel_type, relation.get("head_id"), relation.get("tail_id")
            )
            rejected_rows.append(relation)
            continue

        props = _properties(relation, {
            "head", "head_id", "tail", "tail_id", "relation", "evidence_chunk_ids",
        })
        props["id"] = relation.get("id") or f"rel:{relation.get('head_id')}:{rel_type}:{relation.get('tail_id')}"
        props["source"] = relation.get("source", "extraction")

        # Gộp danh sách evidence_chunk_ids
        chunk_ids = relation.get("evidence_chunk_ids") or []
        if isinstance(chunk_ids, str):
            chunk_ids = [chunk_ids]
        if not chunk_ids and relation.get("chunk_id"):
            chunk_ids = [relation["chunk_id"]]
        evidence_chunk_ids = [str(c) for c in chunk_ids if c]

        relation_rows.append({
            "head_id": relation["head_id"],
            "tail_id": relation["tail_id"],
            "type": rel_type,
            "evidence_chunk_ids": evidence_chunk_ids,
            "props": props,
        })

    # Ghi nhận các quan hệ bị loại bỏ (rejects)
    if rejected_rows:
        if rejects_path is None:
            primary_rejects = base / "loader_rejects.jsonl"
        else:
            primary_rejects = Path(rejects_path)
        primary_rejects.parent.mkdir(parents=True, exist_ok=True)
        with primary_rejects.open("a", encoding="utf-8") as f:
            for row in rejected_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        # Đồng bộ thêm bản sao vào data/extracted/loader_rejects.jsonl nếu thư mục data/extracted tồn tại
        if base.name == "resolved" and (base.parent / "extracted").is_dir():
            ext_rejects = base.parent / "extracted" / "loader_rejects.jsonl"
            with ext_rejects.open("a", encoding="utf-8") as f:
                for row in rejected_rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if store is not None:
        store.run_batches(
            "UNWIND $rows AS row MATCH (a:Entity {id: row.head_id}), (b:Entity {id: row.tail_id}) "
            "CALL apoc.merge.relationship(a, row.type, {id: row.props.id}, row.props, b) YIELD rel "
            "SET rel += row.props "
            "SET rel.evidence_chunk_ids = apoc.coll.toSet(coalesce(rel.evidence_chunk_ids, []) + coalesce(row.evidence_chunk_ids, [])) "
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
        props = _properties(chunk, {"links", "mentions"})
        raw_links = chunk.get("links") or []
        props["links"] = [
            link if isinstance(link, str) else (link.get("target") or link.get("name") or "")
            for link in raw_links
        ]
        props["links"] = [str(lnk) for lnk in props["links"] if lnk]
        chunks.append({
            "id": chunk["id"],
            "page_id": chunk["page_id"],
            "props": props,
            "raw_chunk": chunk,
        })
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
    mentions = []
    # 1. Đọc mentions từ file resolved/mentions.jsonl (nếu có từ bước resolve)
    resolved_mentions = base / "resolved" / "mentions.jsonl"
    if not resolved_mentions.exists():
        resolved_mentions = base / "mentions.jsonl"
    if resolved_mentions.exists():
        for item in _read_jsonl(resolved_mentions) or []:
            c_id = item.get("chunk_id") or item.get("id")
            e_id = item.get("entity_id") or item.get("target_id")
            if c_id and e_id:
                mentions.append({"chunk_id": str(c_id), "entity_id": str(e_id)})

    # 2. Đọc mentions từ raw_chunk nếu links/mentions đã có entity_id
    for row in chunks:
        raw_chunk = row.get("raw_chunk") or {}
        for m in raw_chunk.get("mentions", []):
            if isinstance(m, dict) and m.get("entity_id"):
                mentions.append({"chunk_id": row["id"], "entity_id": str(m["entity_id"])})
            elif isinstance(m, str) and (m.startswith("qid:") or m.startswith("local:")):
                mentions.append({"chunk_id": row["id"], "entity_id": m})

        for link in raw_chunk.get("links", []):
            if isinstance(link, dict) and link.get("entity_id"):
                mentions.append({"chunk_id": row["id"], "entity_id": str(link["entity_id"])})


    # YÊU CẦU: Khớp MENTIONS thuần túy theo ID (Chunk.id -> Entity.id),
    # BỎ HOÀN TOÀN điều kiện so tên / alias
    if mentions:
        store.run_batches(
            "UNWIND $rows AS row "
            "MATCH (c:Chunk {id: row.chunk_id}), (e:Entity {id: row.entity_id}) "
            "MERGE (c)-[:MENTIONS]->(e)",
            mentions,
        )
    store.run(
        "MATCH (a:Article) WHERE a.qid IS NOT NULL MATCH (e:Entity) "
        "WHERE e.id = 'qid:' + a.qid MERGE (a)-[:ABOUT]->(e)"
    )


def link_periods(store) -> None:
    """Tạo (:Entity)-[:IN_PERIOD]->(:Period) theo overlap năm hoặc period_ids fallback,
    và (:Chunk|:Article)-[:IN_PERIOD]->(:Period)."""
    if store is None:
        return

    # 1. Chunk -> Period qua period_ids / period_id
    store.run(
        "MATCH (c:Chunk) UNWIND coalesce(c.period_ids, [c.period_id]) AS period_id "
        "MATCH (p:Period {id: period_id}) MERGE (c)-[:IN_PERIOD]->(p)"
    )
    # 2. Article -> Period qua period_id
    store.run(
        "MATCH (a:Article) WHERE a.period_id IS NOT NULL MATCH (p:Period {id: a.period_id}) "
        "MERGE (a)-[:IN_PERIOD]->(p)"
    )
    # 3. YÊU CẦU 3: Entity có start_year -> overlap năm là nguồn sự thật:
    # period.start <= coalesce(entity.end_year, entity.start_year) AND coalesce(period.end, period.start) >= entity.start_year
    store.run(
        "MATCH (e:Entity), (p:Period) "
        "WHERE e.start_year IS NOT NULL "
        "  AND p.start IS NOT NULL "
        "  AND p.start <= coalesce(e.end_year, e.start_year) "
        "  AND coalesce(p.end, p.start) >= e.start_year "
        "MERGE (e)-[:IN_PERIOD]->(p)"
    )
    # 4. Entity KHÔNG có start_year: fallback qua period_ids nếu có
    store.run(
        "MATCH (e:Entity) WHERE e.start_year IS NULL AND e.period_ids IS NOT NULL "
        "UNWIND e.period_ids AS period_id "
        "MATCH (p:Period {id: period_id}) "
        "MERGE (e)-[:IN_PERIOD]->(p)"
    )


def compute_degree_and_display_names(store) -> None:
    if store is None:
        return
    # 1. Tính bậc đồ thị (degree) và đặt display_name mặc định = name
    store.run(
        "MATCH (e:Entity) OPTIONAL MATCH (e)-[r]-() WITH e, count(DISTINCT r) AS degree "
        "SET e.degree = degree, e.display_name = coalesce(e.name, e.id)"
    )
    # 2. YÊU CẦU 4: Khi phát hiện nhiều Entity cùng name (khác id),
    # set e.display_name = e.name + " (" + toString(e.start_year) + ")" cho các entity có start_year
    store.run(
        "MATCH (e:Entity) WHERE e.name IS NOT NULL "
        "WITH e.name AS name, count(e) AS cnt, collect(e) AS entities "
        "WHERE cnt > 1 "
        "UNWIND entities AS e "
        "WITH e "
        "WHERE e.start_year IS NOT NULL "
        "SET e.display_name = e.name + ' (' + toString(e.start_year) + ')'"
    )

