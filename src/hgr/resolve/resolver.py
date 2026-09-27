"""Hợp nhất thực thể: link→QID → alias dict → fuzzy (blocking type + period) → local id. (M5)"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import yaml

from hgr.config import get_settings


def _clean(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "")).strip()


def _slug(text: str) -> str:
    value = _clean(text).lower().replace("đ", "d")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9\s\-]", "", value)
    value = re.sub(r"\s+", "-", value).strip("-")
    return value or "entity"


class EntityResolver:
    def __init__(self, fuzzy_threshold: int = 92, event_year_tolerance: int = 1):
        self.fuzzy_threshold = fuzzy_threshold
        self.event_year_tolerance = event_year_tolerance
        self.aliases: dict[str, set[str]] = {}
        self.alias_to_id: dict[str, str] = {}

    def add_aliases(self, canonical_id: str, names: list[str]) -> None:
        self.aliases.setdefault(canonical_id, set())
        for name in names:
            if name:
                cleaned = _clean(name)
                self.aliases[canonical_id].add(cleaned)
                self.alias_to_id.setdefault(cleaned.casefold(), canonical_id)

    def resolve(self, entity: dict, chunk_links: list[dict], period_id: str) -> str:
        """→ canonical id (qid:Qxxx | local:<slug>)."""
        qid = entity.get("qid")
        if qid:
            return f"qid:{qid.removeprefix('qid:')}"
        name = _clean(str(entity.get("name") or entity.get("head") or ""))
        if not name:
            return "local:unknown"
        canonical_id = self.alias_to_id.get(name.casefold())
        if canonical_id:
            return canonical_id
        for link in chunk_links:
            target = link if isinstance(link, str) else link.get("target")
            if not target:
                continue
            if _clean(target).casefold() == name.casefold():
                return f"local:{_slug(target)}"
        return f"local:{_slug(name)}"


def run() -> None:
    """extractions + structured → data/resolved/entities.jsonl, relations.jsonl."""
    settings = get_settings()
    project_root = Path(settings.project_root)
    extracted_dir = project_root / settings.paths.data_dir / "extracted"
    resolved_dir = project_root / settings.paths.data_dir / "resolved"
    resolved_dir.mkdir(parents=True, exist_ok=True)

    resolver = EntityResolver(settings.resolve.fuzzy_threshold, settings.resolve.event_year_tolerance)
    backbone_dir = project_root / settings.scope.backbone_dir
    dia_danh_path = backbone_dir / "dia_danh.yaml"
    if dia_danh_path.exists():
        dia_danh = yaml.safe_load(dia_danh_path.read_text(encoding="utf-8")) or {}
        for place in dia_danh.get("dia_danh", []):
            resolver.add_aliases(
                f"local:{place['id']}",
                [place.get("canonical", ""), *(item.get("name", "") for item in place.get("names", []))],
            )

    article_by_name: dict[str, dict] = {}
    chunks_path = project_root / settings.paths.data_dir / "processed" / "chunks.jsonl"
    if chunks_path.exists():
        for line in chunks_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                chunk = json.loads(line)
                article_by_name[chunk["page_title"].casefold()] = {
                    "qid": chunk.get("qid"),
                    "page_id": chunk.get("page_id"),
                    "period_ids": chunk.get("period_ids") or [chunk.get("period_id")],
                }

    entity_by_id: dict[str, dict] = {}
    relation_rows: list[dict] = []

    def register_entity(name: str, entity: dict | None = None, period_ids: list[str] | None = None) -> str:
        entity = entity or {}
        known_article = article_by_name.get(name.casefold(), {})
        qid = entity.get("qid") or known_article.get("qid")
        entity_id = resolver.resolve({"name": name, "qid": qid}, [], "")
        row = entity_by_id.setdefault(entity_id, {
            "id": entity_id,
            "qid": qid,
            "name": name,
            "aliases": [],
            "type": entity.get("type", "Unknown"),
            "description": entity.get("description", ""),
            "period_ids": [],
            "start_year": entity.get("start_year"),
            "end_year": entity.get("end_year"),
        })
        for alias in [name, *entity.get("aliases", [])]:
            if alias and alias not in row["aliases"]:
                row["aliases"].append(alias)
        if row["type"] == "Unknown" and entity.get("type"):
            row["type"] = entity["type"]
        for period_id in period_ids or known_article.get("period_ids", []):
            if period_id and period_id not in row["period_ids"]:
                row["period_ids"].append(period_id)
        for field in ("start_year", "end_year"):
            if row[field] is None and entity.get(field) is not None:
                row[field] = entity[field]
        return entity_id

    chunks_by_id: dict[str, dict] = {}
    if chunks_path.exists():
        for line in chunks_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                chunk = json.loads(line)
                chunks_by_id[chunk["id"]] = chunk

    source = extracted_dir / "extractions.jsonl"
    if source.exists():
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            chunk = chunks_by_id.get(item.get("chunk_id"), {})
            period_ids = chunk.get("period_ids") or [chunk.get("period_id")]
            entity_ids: dict[str, str] = {}
            for ent in item.get("entities", []):
                name = ent.get("name")
                if name:
                    entity_ids[name] = register_entity(name, ent, period_ids)
            for trip in item.get("triplets", []):
                head = str(trip.get("head") or chunk.get("page_title") or "")
                tail = str(trip.get("tail") or "")
                if not head or not tail:
                    continue
                head_id = entity_ids.get(head) or register_entity(
                    head,
                    {"qid": chunk.get("qid"), "type": "Unknown"},
                    period_ids,
                )
                tail_id = entity_ids.get(tail) or register_entity(tail, period_ids=period_ids)
                relation_rows.append({
                    "id": f"rel:{head_id}:{trip.get('relation', 'RELATED_TO')}:{tail_id}",
                    "head_id": head_id,
                    "head": head,
                    "relation": trip.get("relation", "RELATED_TO"),
                    "tail_id": tail_id,
                    "tail": tail,
                    "start_year": trip.get("start_year"),
                    "end_year": trip.get("end_year"),
                    "confidence": trip.get("confidence", 0.7),
                    "evidence": trip.get("evidence", ""),
                    "source": "extraction",
                })

    structured = extracted_dir / "structured.jsonl"
    if structured.exists():
        for line in structured.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            trip = json.loads(line)
            head = str(trip.get("head") or "")
            tail = str(trip.get("tail") or "")
            if not head or not tail:
                continue
            if trip.get("relation") == "CAPITAL_OF":
                head_type, tail_type = "Place", "Polity"
            else:
                head_type, tail_type = "Polity", "Polity"
            head_id = register_entity(head, {"type": head_type, "start_year": trip.get("start_year"), "end_year": trip.get("end_year")})
            tail_id = register_entity(tail, {"type": tail_type, "start_year": trip.get("start_year"), "end_year": trip.get("end_year")})
            relation_rows.append({
                "id": f"rel:{head_id}:{trip.get('relation', 'RELATED_TO')}:{tail_id}",
                "head_id": head_id,
                "head": head,
                "relation": trip.get("relation", "RELATED_TO"),
                "tail_id": tail_id,
                "tail": tail,
                "start_year": trip.get("start_year"),
                "end_year": trip.get("end_year"),
                "confidence": trip.get("confidence", 1.0),
                "evidence": trip.get("evidence", ""),
                "source": "curated",
            })

    out_entities = resolved_dir / "entities.jsonl"
    with out_entities.open("w", encoding="utf-8") as f:
        for row in entity_by_id.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    out_rel = resolved_dir / "relations.jsonl"
    with out_rel.open("w", encoding="utf-8") as f:
        for row in relation_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[OK] {len(entity_by_id)} entity → {out_entities.relative_to(project_root)}")
    print(f"[OK] {len(relation_rows)} relation → {out_rel.relative_to(project_root)}")
