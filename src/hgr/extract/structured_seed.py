"""Triplet không cần LLM: backbone (curated 1.0) + Wikidata + infobox (0.95). (M4)"""
from __future__ import annotations

import glob
from pathlib import Path

import yaml


def from_backbone(backbone_dir: str) -> list[dict]:
    """Tạo triplet từ YAML backbone: kinh đô, triều đại và quốc hiệu."""
    rows: list[dict] = []
    root = Path(backbone_dir)
    for path in sorted(root.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for section, items in data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if section == "kinh_do":
                    place = item.get("place")
                    polity = item.get("polity")
                    if place and polity:
                        rows.append({
                            "head": place,
                            "relation": "CAPITAL_OF",
                            "tail": polity,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"{place} là kinh đô của {polity}",
                        })
                elif section == "trieu_dai":
                    name = item.get("name")
                    period = item.get("period")
                    if name and period:
                        rows.append({
                            "head": name,
                            "relation": "RELATED_TO",
                            "tail": period,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"{name} thuộc thời {period}",
                        })
                elif section == "quoc_hieu":
                    name = item.get("name")
                    if name:
                        rows.append({
                            "head": name,
                            "relation": "RELATED_TO",
                            "tail": "Việt Nam",
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"{name} là quốc hiệu lịch sử",
                        })
    return rows


def from_wikidata(article: dict) -> list[dict]:
    """Đọc các rel Wikidata sẵn trên article, tạo triplet sơ bộ và an toàn."""
    rows: list[dict] = []
    wikidata = article.get("wikidata") or {}
    rels = wikidata.get("rels") or {}
    rel_labels = wikidata.get("rel_labels") or {}
    for rel, qids in rels.items():
        for qid in qids:
            label_info = rel_labels.get(qid) or {}
            label = label_info.get("label") or qid
            rows.append({
                "head": article.get("title"),
                "relation": "RELATED_TO",
                "tail": label,
                "start_year": article.get("start_year"),
                "end_year": article.get("end_year"),
                "confidence": 0.9,
                "evidence": article.get("title", ""),
            })
    return rows


def from_infobox(article: dict, infobox_map: dict) -> list[dict]:
    """Map infobox theo configs/infobox_map.yaml. Không cần LLM."""
    infobox = article.get("infobox") or {}
    rows: list[dict] = []
    template_name = (infobox.get("template") or "").lower()
    rules = infobox_map.get("templates", {})
    for key, rule in rules.items():
        if key.lower() != template_name:
            continue
        for field_name, mapping in rule.items():
            if field_name not in (infobox.get("fields") or {}):
                continue
            field_value = infobox["fields"].get(field_name, {}).get("text")
            if not field_value:
                continue
            rows.append({
                "head": article.get("title"),
                "relation": mapping.get("rel"),
                "tail": field_value,
                "start_year": article.get("start_year"),
                "end_year": article.get("end_year"),
                "confidence": 0.95,
                "evidence": field_value,
            })
    return rows
