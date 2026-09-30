"""Chạy pass 1 (entity) → pass 2 (relation) → kiểm định cho mỗi chunk. (M4)"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from hgr.config import get_settings
from hgr.extract.prompts import (
    PROMPT_VERSION,
    build_entity_messages,
    build_relation_messages,
)
from hgr.extract.schemas import EntityOutput, RelationOutput
from hgr.extract.structured_seed import from_backbone, from_infobox, from_wikidata
from hgr.extract.validator import load_ontology, validate_triplet
from hgr.llm.cache import DiskCache
from hgr.llm.ollama_client import OllamaClient
from hgr.log import get_logger
from hgr.periods import Period, all_periods, load_eras

log = get_logger(__name__)


def _read_jsonl(path: Path | str):
    p = Path(path)
    if not p.exists():
        return
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _get_era_period_ids(era_query: str) -> set[str]:
    """Tra cứu tập hợp period_id thuộc era (so khớp theo id hoặc alias của era)."""
    eras = load_eras()
    target_period_ids: set[str] = set()
    norm_query = era_query.strip().lower()

    for era in eras:
        era_id_norm = era.id.lower()
        era_aliases_norm = [a.lower() for a in era.aliases]
        if norm_query == era_id_norm or norm_query in era_aliases_norm:
            for p in era.periods:
                target_period_ids.add(p.id)

    # Nếu không tìm thấy era nào, có thể era_query chính là một period_id hoặc mã tự do
    if not target_period_ids:
        target_period_ids.add(era_query)

    return target_period_ids


def _resolve_period_context(chunk: dict, period: dict | Period | None) -> dict:
    """Chuẩn hóa thông tin period về dạng dict để truyền vào prompt builders."""
    if isinstance(period, Period):
        return {
            "id": period.id,
            "name": period.name,
            "era_id": period.era_id,
            "role_vocab": period.role_vocab,
            "polities": period.polities,
        }
    if isinstance(period, dict) and period:
        return dict(period)

    # Nếu period không được truyền vào, tìm kiếm theo period_id của chunk
    period_id = chunk.get("period_id")
    if period_id:
        for p in all_periods():
            if p.id == period_id:
                return {
                    "id": p.id,
                    "name": p.name,
                    "era_id": p.era_id,
                    "role_vocab": p.role_vocab,
                    "polities": p.polities,
                }
    return {}


@dataclass
class ExtractResult:
    """Kết quả trích xuất tường minh cho một chunk."""

    chunk_id: str
    entities: list[dict] = field(default_factory=list)
    triplets: list[dict] = field(default_factory=list)
    rejects: list[dict] = field(default_factory=list)
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Chuyển thành dict để ghi ra extractions.jsonl."""
        return {
            "chunk_id": self.chunk_id,
            "entities": self.entities,
            "triplets": self.triplets,
            "rejects": self.rejects,
            "cache_hit": self.cache_hit,
        }


def to_json_dict(result: ExtractResult) -> dict[str, Any]:
    """Hàm chuyển ExtractResult thành dict để serialize JSON."""
    return result.to_dict()


def extract_chunk(
    chunk: dict,
    period: dict | Period | None = None,
    client: OllamaClient | None = None,
    cache: DiskCache | None = None,
    ontology: dict | None = None,
    prompt_version: str = PROMPT_VERSION,
    model: str | None = None,
    max_year: int = 1945,
    record_rejects: bool = True,
    reject_path: str | Path | None = None,
) -> ExtractResult:
    """Trích xuất 2-pass: Pass 1 (Entities) -> Pass 2 (Relations) -> Validator kiểm định.

    - Tích hợp DiskCache theo sha256(model, prompt_version, chunk_id, content).
    - Pass 2 chỉ nhận entities từ Pass 1.
    - Triplet qua validator.validate_triplet; triplet vi phạm được ghi vào rejects.jsonl.
    """
    settings = get_settings()

    # Khởi tạo client nếu chưa truyền vào
    if client is None:
        client = OllamaClient(
            host=settings.llm.host,
            chat_model=settings.llm.chat_model,
            embed_model=settings.llm.embed_model,
            num_ctx=settings.llm.num_ctx,
            temperature=settings.llm.temperature,
            timeout_s=settings.llm.timeout_s,
            max_retries=settings.llm.max_retries,
        )

    # Xác định tên model dùng cho cache key
    if model is None:
        model = getattr(client, "chat_model", None) or settings.llm.chat_model
    model_name = "mock-model" if isinstance(model, MagicMock) else str(model or "default-model")

    # Khởi tạo cache nếu chưa có
    if cache is None:
        cache_dir = Path(settings.project_root) / settings.paths.cache_dir
        cache = DiskCache(cache_dir)

    if ontology is None:
        ontology = load_ontology()

    chunk_id = str(chunk.get("id") or chunk.get("chunk_id") or "")
    chunk_content = str(chunk.get("text") or "")
    period_ctx = _resolve_period_context(chunk, period)

    # ==================== PASS 1: ENTITIES ====================
    cache_key_pass1 = DiskCache.make_key(model_name, prompt_version, chunk_id, chunk_content)
    cached_pass1 = cache.get(cache_key_pass1) if cache is not None else None
    pass1_cache_hit = False

    if cached_pass1 is not None and isinstance(cached_pass1, dict) and "entities" in cached_pass1:
        entities_raw = cached_pass1["entities"]
        pass1_cache_hit = True
    else:
        messages1 = build_entity_messages(chunk, period=period_ctx)
        out1: EntityOutput = client.chat_json(messages1, EntityOutput)
        entities_raw = [
            e.model_dump(exclude_none=True) if hasattr(e, "model_dump") else dict(e)
            for e in (out1.entities if hasattr(out1, "entities") else [])
        ]
        if cache is not None:
            cache.set(cache_key_pass1, {"entities": entities_raw})

    # Chuẩn hóa entities
    entities: list[dict] = []
    for e in entities_raw:
        ent_dict = dict(e)
        if hasattr(ent_dict.get("type"), "value"):
            ent_dict["type"] = ent_dict["type"].value
        entities.append(ent_dict)

    # ==================== PASS 2: RELATIONS ====================
    # Pass 2 phụ thuộc vào entities của Pass 1 -> băm entities để tạo cache key độc lập
    serialized_pass1 = json.dumps(entities, sort_keys=True, ensure_ascii=False)
    pass1_hash = hashlib.sha256(serialized_pass1.encode("utf-8")).hexdigest()[:16]
    pass2_version = f"{prompt_version}:relations:{pass1_hash}"

    cache_key_pass2 = DiskCache.make_key(model_name, pass2_version, chunk_id, chunk_content)
    cached_pass2 = cache.get(cache_key_pass2) if cache is not None else None
    pass2_cache_hit = False

    if cached_pass2 is not None and isinstance(cached_pass2, dict) and "triplets" in cached_pass2:
        raw_triplets = cached_pass2["triplets"]
        pass2_cache_hit = True
    else:
        messages2 = build_relation_messages(chunk, entities=entities, period=period_ctx)
        out2: RelationOutput = client.chat_json(messages2, RelationOutput)
        raw_triplets = [
            t.model_dump(exclude_none=True) if hasattr(t, "model_dump") else dict(t)
            for t in (out2.triplets if hasattr(out2, "triplets") else [])
        ]
        if cache is not None:
            cache.set(cache_key_pass2, {"triplets": raw_triplets})

    # ==================== VALIDATION & REJECTS ====================
    valid_triplets: list[dict] = []
    rejected_triplets: list[dict] = []

    for trip in raw_triplets:
        trip_dict = dict(trip)
        if hasattr(trip_dict.get("relation"), "value"):
            trip_dict["relation"] = trip_dict["relation"].value
        if "chunk_id" not in trip_dict and chunk_id:
            trip_dict["chunk_id"] = chunk_id
        if "source" not in trip_dict:
            trip_dict["source"] = "llm"

        val_res = validate_triplet(
            trip_dict,
            entities=entities,
            chunk_text=chunk_content,
            ontology=ontology,
            max_year=max_year,
            chunk_id=chunk_id,
            record_rejects=record_rejects,
            reject_path=reject_path,
        )
        if val_res["ok"]:
            valid_triplets.append(trip_dict)
        else:
            rejected_triplets.append({
                "triplet": trip_dict,
                "reasons": val_res["reasons"],
            })

    return ExtractResult(
        chunk_id=chunk_id,
        entities=entities,
        triplets=valid_triplets,
        rejects=rejected_triplets,
        cache_hit=pass1_cache_hit and pass2_cache_hit,
    )


def run_structured(
    root: Path,
    settings: Any,
    era: str | None = None,
    period: str | None = None,
    ontology: dict | None = None,
    articles_path: Path | str | None = None,
    backbone_dir: Path | str | None = None,
) -> list[dict]:
    """Trích xuất quan hệ Tier S (backbone, wikidata, infobox) không cần LLM."""
    if ontology is None:
        ontology = load_ontology()

    b_dir = Path(backbone_dir) if backbone_dir else Path(settings.project_root) / settings.scope.backbone_dir
    all_structured: list[dict] = []

    # 1. From Backbone YAML
    if b_dir.exists():
        bb_rows = from_backbone(str(b_dir), ontology=ontology)
        for r in bb_rows:
            r["source"] = "backbone"
        all_structured.extend(bb_rows)

    # 2. From Wikidata & Infobox (nếu có articles.jsonl)
    art_path = Path(articles_path) if articles_path else Path(settings.project_root) / settings.paths.data_dir / "processed" / "articles.jsonl"
    if art_path.exists():
        era_periods = _get_era_period_ids(era) if era else None
        for article in _read_jsonl(art_path):
            p_id = article.get("period_id")
            if period and p_id != period:
                continue
            if era_periods and p_id not in era_periods and article.get("era_id") != era:
                continue

            wiki_rows = from_wikidata(article, ontology=ontology)
            for r in wiki_rows:
                r["source"] = "wikidata"
            all_structured.extend(wiki_rows)

            info_rows = from_infobox(article, ontology=ontology)
            for r in info_rows:
                r["source"] = "infobox"
            all_structured.extend(info_rows)

    out = root / "structured.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for row in all_structured:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    log.info("[Tier S] Đã trích xuất %d triplet structured -> %s", len(all_structured), out)
    return all_structured


def run(
    era: str | None = None,
    period: str | None = None,
    tier: str | None = None,
    structured: bool = False,
    client: OllamaClient | None = None,
    cache: DiskCache | None = None,
    chunks_path: Path | str | None = None,
    articles_path: Path | str | None = None,
    backbone_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> dict:
    """Điều phối toàn bộ quá trình trích xuất Part B.

    - `--structured`: Chỉ chạy Tier S (backbone, wikidata, infobox).
    - Mặc định: Chạy cả Tier S lẫn vòng lặp LLM 2-pass cho các chunk.
    - Hỗ trợ resume: Tự động bỏ qua các chunk đã có trong extractions.jsonl.
    - Stream output: Ghi từng chunk ra extractions.jsonl và flush ngay lập tức.
    - Bắt lỗi theo chunk: Ghi các chunk lỗi vào failed_chunks.jsonl và tiếp tục job.
    """
    settings = get_settings()
    root = Path(output_dir) if output_dir else Path(settings.project_root) / settings.paths.data_dir / "extracted"
    root.mkdir(parents=True, exist_ok=True)

    # 1. Chạy Tier S
    structured_rows = run_structured(
        root=root,
        settings=settings,
        era=era,
        period=period,
        articles_path=articles_path,
        backbone_dir=backbone_dir,
    )

    if structured:
        print(f"[OK] Hoàn tất Tier S: {len(structured_rows)} triplet -> {root / 'structured.jsonl'}")
        return {
            "structured_triplets": len(structured_rows),
            "processed": 0,
            "cache_hits": 0,
            "errors": 0,
            "validator_rejects": 0,
            "skipped_resume": 0,
        }

    # 2. Chuẩn bị nguồn chunks
    source = Path(chunks_path) if chunks_path else Path(settings.project_root) / settings.paths.data_dir / "processed" / "chunks.jsonl"
    if not source.exists():
        raise FileNotFoundError(f"Chưa có file chunks tại: {source}; hãy chạy 'hgr chunk' trước.")

    extractions_path = root / "extractions.jsonl"
    failed_chunks_path = root / "failed_chunks.jsonl"
    rejects_path = root / "rejects.jsonl"

    # 3. Thu thập các chunk đã xử lý trước đó để hỗ trợ resume
    existing_chunk_ids: set[str] = set()
    if extractions_path.exists():
        for row in _read_jsonl(extractions_path):
            cid = row.get("chunk_id") or row.get("id")
            if cid:
                existing_chunk_ids.add(cid)

    # 4. Xác định danh sách period_id hợp lệ nếu có lọc theo era
    era_periods = _get_era_period_ids(era) if era else None

    processed_count = 0
    cache_hit_count = 0
    error_count = 0
    validator_reject_count = 0
    skipped_count = 0

    ontology = load_ontology()

    # 5. Vòng lặp stream từng chunk qua LLM
    with open(extractions_path, "a", encoding="utf-8") as out_f:
        for chunk in _read_jsonl(source):
            cid = str(chunk.get("id") or chunk.get("chunk_id") or "")
            if not cid:
                continue

            # Lọc era
            if era_periods is not None:
                chunk_p = chunk.get("period_id")
                if chunk_p not in era_periods and chunk.get("era_id") != era:
                    continue

            # Lọc period
            if period and chunk.get("period_id") != period:
                continue

            # Lọc tier
            if tier and chunk.get("tier") != tier:
                continue

            # Resume: bỏ qua chunk đã xử lý
            if cid in existing_chunk_ids:
                skipped_count += 1
                continue

            try:
                res = extract_chunk(
                    chunk=chunk,
                    client=client,
                    cache=cache,
                    ontology=ontology,
                    prompt_version=prompt_version,
                    record_rejects=True,
                    reject_path=rejects_path,
                )
                out_f.write(json.dumps(res.to_dict(), ensure_ascii=False) + "\n")
                out_f.flush()
                existing_chunk_ids.add(cid)

                processed_count += 1
                if res.cache_hit:
                    cache_hit_count += 1
                validator_reject_count += len(res.rejects)

            except Exception as e:
                error_count += 1
                log.warning("Lỗi trích xuất chunk %s: %s (%s)", cid, e, type(e).__name__)
                err_entry = {
                    "chunk_id": cid,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "chunk": chunk,
                }
                with open(failed_chunks_path, "a", encoding="utf-8") as err_f:
                    err_f.write(json.dumps(err_entry, ensure_ascii=False) + "\n")
                    err_f.flush()

    summary = {
        "processed": processed_count,
        "skipped_resume": skipped_count,
        "cache_hits": cache_hit_count,
        "errors": error_count,
        "validator_rejects": validator_reject_count,
        "structured_triplets": len(structured_rows),
    }

    print(
        f"[EXTRACT SUMMARY] Xử lý: {processed_count}, Bỏ qua (resume): {skipped_count}, "
        f"Cache hit: {cache_hit_count}, Lỗi: {error_count}, "
        f"Triplet bị loại: {validator_reject_count}, Tier S: {len(structured_rows)}"
    )
    return summary
