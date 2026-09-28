"""Kiểm định: domain→range (ontology.yaml), evidence ⊂ chunk (rapidfuzz), năm hợp lệ, cutoff 1945, confidence. (M4)"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
import yaml
from rapidfuzz import fuzz

try:
    from hgr.config import CONFIG_DIR, PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    CONFIG_DIR = PROJECT_ROOT / "configs"

DEFAULT_REJECTS_PATH = PROJECT_ROOT / "data" / "extracted" / "rejects.jsonl"


@lru_cache(maxsize=1)
def load_ontology(path: str | Path | None = None) -> dict:
    """Đọc configs/ontology.yaml làm nguồn sự thật duy nhất cho quan hệ và ràng buộc.

    Báo lỗi rõ ràng nếu file thiếu hoặc lỗi cú pháp; không lặng lẽ dùng mặc định.
    """
    ontology_path = Path(path) if path is not None else CONFIG_DIR / "ontology.yaml"

    if not ontology_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file ontology tại: {ontology_path}")

    try:
        data = yaml.safe_load(ontology_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Lỗi khi đọc file ontology tại {ontology_path}: {e}") from e

    if not isinstance(data, dict) or "relations" not in data:
        raise ValueError(f"Cấu trúc ontology không hợp lệ (thiếu 'relations'): {ontology_path}")

    return data


def _norm(v: str) -> str:
    """Chuẩn hóa Unicode NFC, khoảng trắng và chữ thường."""
    text = unicodedata.normalize("NFC", str(v or ""))
    return re.sub(r"\s+", " ", text).strip().lower()


def _guess_type(name: str, entities: dict | None = None, fallback: str = "Unknown") -> str:
    entities = entities or {}
    key = _norm(name)
    if not key:
        return fallback
    for k, val in entities.items():
        if isinstance(val, dict) and _norm(k) == key:
            t = val.get("type") or val.get("kind")
            if t:
                return str(t)
        elif isinstance(val, str) and _norm(k) == key and val:
            return val
    if any(token in key for token in ("vua", "hoàng", "thánh", "tướng", "thiền", "giáo", "nhà cách mạng", "nữ vương", "quốc vương", "chủ tịch", "thủ tướng", "đô đốc", "tiết độ sứ")):
        return "Person"
    if any(token in key for token in ("thành", "sông", "núi", "động", "hà nội", "hải phòng", "huế", "đà nẵng", "kinh đô", "địa danh", "đô thị", "nơi sinh", "nơi mất", "cổ loa", "phong châu", "hoa lư", "thăng long", "đông kinh", "bạch đằng")):
        return "Place"
    if any(token in key for token in ("triều", "nhà", "quốc gia", "vương quốc", "nước", "đế quốc", "văn lang", "âu lạc", "đại việt", "đại nam", "đại cồ việt", "đại ngu")):
        return "Polity"
    if any(token in key for token in ("chiến", "trận", "khởi nghĩa", "hòa ước", "dựng nước", "cách mạng", "đại hội", "biến cố", "binh biến")):
        return "Event"
    if any(token in key for token in ("đảng", "hội", "mặt trận", "đoàn")):
        return "Organization"
    if any(token in key for token in ("sách", "chiếu", "hịch", "truyền kỳ", "sử ký", "bình ngô", "luật")):
        return "Work"
    if any(token in key for token in ("văn hóa", "khảo cổ")):
        return "Culture"
    return fallback


def _add_reason(reasons: list[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


def validate_triplet(
    triplet: dict,
    entities: dict | list | str | None = None,
    chunk_text: str | None = None,
    ontology: dict | None = None,
    max_year: int = 1945,
    chunk_id: str | None = None,
    record_rejects: bool = False,
    reject_path: str | Path | None = None,
) -> dict:
    """→ {'ok': bool, 'reasons': [..]}.

    Hỗ trợ cả cú pháp cũ `validate_triplet(triplet, chunk_text, ...)` và cú pháp có entity map.
    Nguồn ontology đọc duy nhất từ configs/ontology.yaml (hoặc ontology truyền vào).
    """
    if isinstance(entities, str):
        chunk_text, entities = entities, {}
    elif isinstance(entities, list):
        ent_map = {}
        for item in entities:
            if isinstance(item, dict) and "name" in item:
                ent_map[item["name"]] = item.get("type") or item
        entities = ent_map
    else:
        entities = entities or {}

    if chunk_text is None:
        chunk_text = ""

    if ontology is None:
        ontology = load_ontology()

    reasons: list[str] = []

    # 1. Kiểm tra head / tail
    head = str(triplet.get("head") or "").strip()
    tail = str(triplet.get("tail") or "").strip()
    if not head or not tail:
        _add_reason(reasons, "head_or_tail_missing")

    # 2. Kiểm tra quan hệ theo ontology.yaml
    rel = triplet.get("relation")
    if rel is None or rel == "":
        _add_reason(reasons, "relation_missing")
    else:
        all_rels = ontology.get("relations", {})
        if rel not in all_rels:
            _add_reason(reasons, "relation_not_in_ontology")
        else:
            rel_def = all_rels[rel]
            domain = rel_def.get("domain", ["*"])
            range_ = rel_def.get("range", ["*"])

            head_type = _guess_type(head, entities)
            tail_type = _guess_type(tail, entities)

            if head_type != "Unknown" and "*" not in domain and head_type not in domain:
                _add_reason(reasons, "head_type_invalid")
            if tail_type != "Unknown" and "*" not in range_ and tail_type not in range_:
                _add_reason(reasons, "tail_type_invalid")

    # 3. So evidence với chunk_text bằng rapidfuzz (partial_ratio >= 90.0)
    evidence = str(triplet.get("evidence") or "").strip()
    chunk = str(chunk_text or "")
    if evidence:
        evidence_norm = _norm(evidence)
        chunk_norm = _norm(chunk)
        if not chunk_norm:
            _add_reason(reasons, "evidence_not_in_chunk")
        else:
            sim = fuzz.partial_ratio(evidence_norm, chunk_norm)
            if sim < 90.0:
                _add_reason(reasons, "evidence_not_in_chunk")
    else:
        _add_reason(reasons, "evidence_not_in_chunk")

    # 4. Kiểm tra confidence
    conf = triplet.get("confidence")
    if conf is not None:
        try:
            if float(conf) < 0.6:
                _add_reason(reasons, "low_confidence")
        except (TypeError, ValueError):
            _add_reason(reasons, "invalid_confidence")

    # 5. Kiểm tra thời gian và cutoff 1945
    for key in ("start_year", "end_year"):
        val = triplet.get(key)
        if val is not None:
            try:
                year = int(val)
            except (TypeError, ValueError):
                _add_reason(reasons, "year_not_integer")
                continue
            if year > max_year:
                _add_reason(reasons, "after_1945")

    if triplet.get("start_year") is not None and triplet.get("end_year") is not None:
        try:
            if int(triplet["start_year"]) > int(triplet["end_year"]):
                _add_reason(reasons, "start_year_gt_end_year")
        except (TypeError, ValueError):
            pass

    ok = len(reasons) == 0
    if not ok and record_rejects:
        record_reject(triplet, reasons, chunk_id=chunk_id, reject_path=reject_path)

    return {"ok": ok, "reasons": reasons}


def record_reject(
    triplet: dict,
    reasons: list[str],
    chunk_id: str | None = None,
    reject_path: str | Path | None = None,
) -> None:
    """Ghi triplet bị loại kèm chunk_id và danh sách mã lý do vào file JSONL (nối tiếp)."""
    out_path = Path(reject_path) if reject_path is not None else DEFAULT_REJECTS_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cid = chunk_id or triplet.get("chunk_id")
    row = {
        "chunk_id": cid,
        "triplet": triplet,
        "reasons": reasons,
    }
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def get_rejection_stats(reject_path: str | Path | None = None) -> dict[str, int]:
    """Đọc file rejects.jsonl và trả về thống kê số lần xuất hiện của từng mã lý do loại bỏ."""
    in_path = Path(reject_path) if reject_path is not None else DEFAULT_REJECTS_PATH
    if not in_path.exists():
        return {}
    stats: dict[str, int] = {}
    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                for reason in row.get("reasons", []):
                    stats[reason] = stats.get(reason, 0) + 1
            except json.JSONDecodeError:
                continue
    return stats
