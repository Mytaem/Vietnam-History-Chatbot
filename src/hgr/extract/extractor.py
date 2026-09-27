"""Chạy pass 1 (entity) → pass 2 (relation) → (pass 3 gleaning) cho mỗi chunk. (M4)"""
from __future__ import annotations

import json
from pathlib import Path

from hgr.config import get_settings
from hgr.extract.structured_seed import from_backbone


def _read_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def extract_chunk(chunk: dict, period: dict | None = None) -> dict:
    """→ {chunk_id, entities[], triplets[], rejects[]}.

    Phiên bản khởi động: không dùng LLM, chỉ sinh triplet từ wikilink + metadata chunk; đủ để
    M4 chạy được và cung cấp dữ liệu cơ bản cho các bước sau.
    """
    entities: list[dict] = []
    for link in chunk.get("links", []):
        target = link if isinstance(link, str) else link.get("target")
        if target:
            entities.append({"name": target, "type": "Place"})
    if chunk.get("page_title"):
        entities.append({"name": chunk["page_title"], "type": "Person"})

    triplets: list[dict] = []
    for link in chunk.get("links", []):
        target = link if isinstance(link, str) else link.get("target")
        if not target:
            continue
        evidence = chunk.get("text") or ""
        first_sentence = evidence.split(".", 1)[0].strip()
        triplets.append({
            "head": chunk.get("page_title"),
            "relation": "RELATED_TO",
            "tail": target,
            "start_year": chunk.get("min_year"),
            "end_year": chunk.get("max_year"),
            "evidence": first_sentence or evidence[:160],
            "confidence": 0.7,
        })
    return {"chunk_id": chunk.get("id"), "entities": entities, "triplets": triplets, "rejects": []}


def run(era: str | None = None, period: str | None = None, tier: str | None = None,
        structured: bool = False) -> None:
    """Lưu triplet từ chunk sang data/extracted/*.jsonl.

    - `--structured`: sinh từ backbone YAML, không cần LLM.
    - Mặc định: dùng heuristic từ chunk hiện có.
    """
    settings = get_settings()
    root = Path(settings.project_root) / settings.paths.data_dir / "extracted"
    root.mkdir(parents=True, exist_ok=True)

    if structured:
        backbone_dir = Path(settings.project_root) / settings.scope.backbone_dir
        rows = from_backbone(str(backbone_dir))
        out = root / "structured.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[OK] {len(rows)} triplet backbone → {out.relative_to(settings.project_root)}")
        return

    source = Path(settings.project_root) / settings.paths.data_dir / "processed" / "chunks.jsonl"
    if not source.exists():
        raise FileNotFoundError("Chưa có data/processed/chunks.jsonl; hãy chạy 'hgr chunk' trước.")

    results = []
    for chunk in _read_jsonl(source):
        if era and chunk.get("period_id", "").startswith(era):
            pass
        elif era and chunk.get("period_id") not in (era,):
            continue
        if period and chunk.get("period_id") != period:
            continue
        if tier and chunk.get("tier") != tier:
            continue
        results.append(extract_chunk(chunk))

    out = root / "extractions.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[OK] {len(results)} chunk → {out.relative_to(settings.project_root)}")
