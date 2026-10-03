"""Triplet không cần LLM: backbone (curated 1.0) + Wikidata + infobox (0.95). (M4)"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from typing import Any

import yaml

# Khởi tạo đường dẫn configs
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "configs"

# Biến đếm các thuộc tính Wikidata không có ánh xạ sang ontology
_UNMAPPED_WIKIDATA_COUNTS: Counter[str] = Counter()


def get_unmapped_wikidata_counts() -> dict[str, int]:
    """Trả về thống kê số lần các thuộc tính Wikidata bị bỏ qua vì không có ánh xạ."""
    return dict(_UNMAPPED_WIKIDATA_COUNTS)


def reset_unmapped_wikidata_counts() -> None:
    """Reset bộ đếm thuộc tính Wikidata chưa ánh xạ."""
    _UNMAPPED_WIKIDATA_COUNTS.clear()


@lru_cache(maxsize=1)
def load_ontology(path: str | Path | None = None) -> dict:
    """Đọc configs/ontology.yaml để kiểm tra quan hệ hợp lệ."""
    ontology_path = Path(path) if path is not None else CONFIG_DIR / "ontology.yaml"
    if not ontology_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file ontology tại: {ontology_path}")
    data = yaml.safe_load(ontology_path.read_text(encoding="utf-8")) or {}
    return data


@lru_cache(maxsize=1)
def load_infobox_map(path: str | Path | None = None) -> dict:
    """Đọc configs/infobox_map.yaml."""
    map_path = Path(path) if path is not None else CONFIG_DIR / "infobox_map.yaml"
    if not map_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file infobox_map tại: {map_path}")
    data = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    return data


def _norm_text(text: str) -> str:
    """Chuẩn hóa Unicode NFC, khoảng trắng và chữ thường."""
    norm = unicodedata.normalize("NFC", str(text or ""))
    return re.sub(r"\s+", " ", norm).strip().lower()


def _normalize_infobox_field_key(key: str) -> str:
    """Chuẩn hóa tên trường infobox: NFC, lowercase, loại bỏ số và khoảng trắng/gạch dưới ở cuối.

    Ví dụ: 'chỉ huy 1' -> 'chỉ huy', 'bên tham chiến_2' -> 'bên tham chiến'.
    """
    key_norm = _norm_text(key)
    return re.sub(r"[\s_]*\d+$", "", key_norm)


# Bảng ánh xạ thuộc tính Wikidata sang quan hệ ontology (Domain -> Range kiểm tra chiều)
# Mỗi entry chứa:
# - rel: Tên quan hệ trong ontology.yaml (tuyệt đối không dùng RELATED_TO)
# - head_is_target: bool
#     False: head = article_title, tail = target_label
#     True:  head = target_label, tail = article_title
# - description: Ý nghĩa ngữ nghĩa của thuộc tính Wikidata
WIKIDATA_REL_MAP: dict[str, dict[str, Any]] = {
    # Gia đình (Person -> Person)
    "P22": {"rel": "CHILD_OF", "head_is_target": False, "description": "cha (article CHILD_OF target)"},
    "P25": {"rel": "CHILD_OF", "head_is_target": False, "description": "mẹ (article CHILD_OF target)"},
    "P26": {"rel": "SPOUSE_OF", "head_is_target": False, "description": "vợ/chồng (article SPOUSE_OF target)"},
    "P40": {"rel": "CHILD_OF", "head_is_target": True, "description": "con cái (target CHILD_OF article)"},
    # Kế thừa/tiền nhiệm/kế nhiệm (Person/Polity -> Person/Polity)
    "P1365": {"rel": "SUCCEEDED", "head_is_target": False, "description": "thay thế cho (article kế nhiệm target)"},
    "P1366": {"rel": "SUCCEEDED", "head_is_target": True, "description": "được thay thế bởi (target kế nhiệm article)"},
    "P155": {"rel": "SUCCEEDED", "head_is_target": False, "description": "tiếp sau / follows (article kế thừa target)"},
    "P156": {"rel": "SUCCEEDED", "head_is_target": True, "description": "được tiếp sau / followed by (target kế thừa article)"},
    # Sự kiện & Địa điểm (Event -> Place)
    "P276": {"rel": "OCCURRED_AT", "head_is_target": False, "description": "địa điểm diễn ra (article OCCURRED_AT target)"},
    # Tham chiến / Tham gia sự kiện (Person/Polity/Org -> Event)
    "P710": {"rel": "PARTICIPATED_IN", "head_is_target": True, "description": "bên tham gia (target PARTICIPATED_IN article)"},
    "P607": {"rel": "PARTICIPATED_IN", "head_is_target": False, "description": "xung đột/chiến dịch (article PARTICIPATED_IN target)"},
    # Sáng lập (Person -> Polity/Org/Place)
    "P112": {"rel": "FOUNDED", "head_is_target": True, "description": "người sáng lập (target FOUNDED article)"},
    # Kinh đô (Place -> Polity)
    "P36": {"rel": "CAPITAL_OF", "head_is_target": True, "description": "thủ đô/kinh đô (target CAPITAL_OF article)"},
    # Sinh / Mất (Person -> Place)
    "P19": {"rel": "BORN_IN", "head_is_target": False, "description": "nơi sinh (article BORN_IN target)"},
    "P20": {"rel": "DIED_IN", "head_is_target": False, "description": "nơi mất (article DIED_IN target)"},
    # Tác giả (Person -> Work)
    "P50": {"rel": "AUTHORED", "head_is_target": True, "description": "tác giả (target AUTHORED article)"},
    # Tổ chức (Person -> Polity/Org)
    "P463": {"rel": "MEMBER_OF", "head_is_target": False, "description": "thành viên tổ chức (article MEMBER_OF target)"},
    # Thành phần (Event/Place -> Event/Place)
    "P361": {"rel": "PART_OF", "head_is_target": False, "description": "là một phần của (article PART_OF target)"},
    "P527": {"rel": "PART_OF", "head_is_target": True, "description": "bao gồm thành phần (target PART_OF article)"},
}


def from_backbone(backbone_dir: str, ontology: dict | None = None) -> list[dict]:
    """Tạo triplet từ YAML backbone: kinh đô, triều đại và quốc hiệu.

    Quan hệ sinh ra phải thuộc ontology (CAPITAL_OF, SUCCEEDED, FOUNDED, RULED...).
    Tuyệt đối không dùng quan hệ RELATED_TO.
    """
    if ontology is None:
        ontology = load_ontology()

    valid_relations = set(ontology.get("relations", {}).keys())

    rows: list[dict] = []
    root = Path(backbone_dir)
    for path in sorted(root.glob("*.yaml")):
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        for section, items in data.items():
            if not isinstance(items, list):
                continue

            if section == "kinh_do":
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    place = item.get("place")
                    polity = item.get("polity")
                    if place and polity and "CAPITAL_OF" in valid_relations:
                        rows.append({
                            "head": place,
                            "relation": "CAPITAL_OF",
                            "tail": polity,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"backbone:kinh_do:{place} là kinh đô của {polity}",
                            "source": "backbone",
                        })

            elif section in ("trieu_dai", "quoc_hieu"):
                # 1. Xử lý các quan hệ cụ thể trong từng phần tử nếu có
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if not name:
                        continue

                    # Người sáng lập -> triều đại/quốc gia
                    founder = item.get("founder")
                    if founder and "FOUNDED" in valid_relations:
                        rows.append({
                            "head": founder,
                            "relation": "FOUNDED",
                            "tail": name,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"backbone:{section}:{founder} sáng lập {name}",
                            "source": "backbone",
                        })

                    # Vua/quân vương trị vì
                    ruler = item.get("ruler") or item.get("king")
                    if ruler and "RULED" in valid_relations:
                        rows.append({
                            "head": ruler,
                            "relation": "RULED",
                            "tail": name,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"backbone:{section}:{ruler} trị vì {name}",
                            "source": "backbone",
                        })

                    # Kinh đô
                    capital = item.get("capital")
                    if capital and "CAPITAL_OF" in valid_relations:
                        rows.append({
                            "head": capital,
                            "relation": "CAPITAL_OF",
                            "tail": name,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"backbone:{section}:{capital} là kinh đô của {name}",
                            "source": "backbone",
                        })

                    # Tiền nhiệm trực tiếp được khai báo
                    predecessor = item.get("predecessor")
                    if predecessor and predecessor != name and "SUCCEEDED" in valid_relations:
                        rows.append({
                            "head": name,
                            "relation": "SUCCEEDED",
                            "tail": predecessor,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"backbone:{section}:{name} kế thừa {predecessor}",
                            "source": "backbone",
                        })

                    # Kế nhiệm trực tiếp được khai báo
                    successor = item.get("successor")
                    if successor and successor != name and "SUCCEEDED" in valid_relations:
                        rows.append({
                            "head": successor,
                            "relation": "SUCCEEDED",
                            "tail": name,
                            "start_year": item.get("start"),
                            "end_year": item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"backbone:{section}:{successor} kế thừa {name}",
                            "source": "backbone",
                        })

                # 2. Xử lý chuỗi kế tục thời gian liên tiếp (SUCCEEDED) giữa các thực thể khác tên
                if "SUCCEEDED" in valid_relations and len(items) > 1:
                    for i in range(1, len(items)):
                        prev_item = items[i - 1]
                        curr_item = items[i]
                        if not isinstance(prev_item, dict) or not isinstance(curr_item, dict):
                            continue
                        prev_name = prev_item.get("name")
                        curr_name = curr_item.get("name")
                        if not prev_name or not curr_name or prev_name == curr_name:
                            continue

                        # Tránh tạo trùng nếu đã khai báo predecessor rõ ràng
                        if curr_item.get("predecessor") == prev_name:
                            continue

                        rows.append({
                            "head": curr_name,
                            "relation": "SUCCEEDED",
                            "tail": prev_name,
                            "start_year": curr_item.get("start"),
                            "end_year": curr_item.get("end"),
                            "confidence": 1.0,
                            "evidence": f"backbone:{section}:{curr_name} kế tục {prev_name}",
                            "source": "backbone",
                        })

    return rows


def from_wikidata(
    article: dict,
    ontology: dict | None = None,
    stats: dict[str, int] | None = None,
    return_dropped: bool = False,
) -> list[dict] | tuple[list[dict], dict[str, int]]:
    """Đọc các rel Wikidata sẵn trên article, tạo triplet đúng chiều và quan hệ ontology.

    Thuộc tính không có trong WIKIDATA_REL_MAP bị bỏ qua và đếm, tuyệt đối không gán RELATED_TO.
    """
    if ontology is None:
        ontology = load_ontology()

    valid_relations = set(ontology.get("relations", {}).keys())

    rows: list[dict] = []
    dropped: Counter[str] = Counter()

    article_title = article.get("title")
    if not article_title:
        if return_dropped:
            return rows, dict(dropped)
        return rows

    article_id = article.get("page_id") or article.get("article_id") or article.get("id")
    chunk_id = article.get("chunk_id")
    start_year = article.get("start_year")
    end_year = article.get("end_year")

    wikidata = article.get("wikidata") or {}
    rels = wikidata.get("rels") or {}
    rel_labels = wikidata.get("rel_labels") or {}

    for prop_id, qids in rels.items():
        mapping = WIKIDATA_REL_MAP.get(prop_id)

        # Thuộc tính không có trong bảng ánh xạ hoặc relation không thuộc ontology
        if not mapping or mapping.get("rel") not in valid_relations or mapping.get("rel") == "RELATED_TO":
            num_dropped = len(qids) if isinstance(qids, list) else 1
            dropped[prop_id] += num_dropped
            _UNMAPPED_WIKIDATA_COUNTS[prop_id] += num_dropped
            if stats is not None:
                stats[prop_id] = stats.get(prop_id, 0) + num_dropped
            continue

        rel_name = mapping["rel"]
        head_is_target = mapping.get("head_is_target", False)

        qid_list = qids if isinstance(qids, list) else [qids]
        for qid in qid_list:
            label_info = rel_labels.get(qid) or {}
            label = (label_info.get("label") if isinstance(label_info, dict) else None) or qid
            if not label or label == article_title:
                continue

            if head_is_target:
                head = label
                tail = article_title
            else:
                head = article_title
                tail = label

            triplet = {
                "head": head,
                "relation": rel_name,
                "tail": tail,
                "start_year": start_year,
                "end_year": end_year,
                # start_year/end_year ở trên là năm của BÀI VIẾT CHỦ THỂ (article_title), không phải của
                # thực thể còn lại (vd P710: head=bên tham chiến, tail=article_title=sự kiện -> năm thuộc
                # tail). year_target cho biết năm này thuộc head hay tail, để resolver không gán nhầm.
                "year_target": "tail" if head_is_target else "head",
                "confidence": 0.95,
                "evidence": f"wikidata:{prop_id}",
                "source": "wikidata",
            }
            if article_id is not None:
                triplet["article_id"] = article_id
            if chunk_id is not None:
                triplet["chunk_id"] = chunk_id

            rows.append(triplet)

    if return_dropped:
        return rows, dict(dropped)
    return rows


def from_infobox(
    article: dict,
    infobox_map: dict | None = None,
    ontology: dict | None = None,
) -> list[dict]:
    """Map infobox theo configs/infobox_map.yaml và configs/ontology.yaml.

    Đổi head/tail theo cấu hình subject/object trong infobox_map.yaml:
    - subject: value, object: page -> head = value, tail = page (ví dụ COMMANDED, CAPITAL_OF)
    - subject: page, object: value -> head = page, tail = value
    Mọi quan hệ sinh ra phải thuộc ontology, không gán RELATED_TO.
    """
    if infobox_map is None:
        infobox_map = load_infobox_map()
    if ontology is None:
        ontology = load_ontology()

    valid_relations = set(ontology.get("relations", {}).keys())

    infobox = article.get("infobox") or {}
    article_title = article.get("title")
    if not article_title:
        return []

    article_id = article.get("page_id") or article.get("article_id") or article.get("id")
    chunk_id = article.get("chunk_id")
    start_year = article.get("start_year")
    end_year = article.get("end_year")

    raw_template = infobox.get("template") or ""
    template_name = _norm_text(raw_template)
    templates_cfg = infobox_map.get("templates", {})

    target_rules: dict[str, dict] | None = None
    for tmpl_key, rules in templates_cfg.items():
        if _norm_text(tmpl_key) == template_name:
            target_rules = rules
            break

    if not target_rules:
        return []

    norm_rules = {_normalize_infobox_field_key(k): v for k, v in target_rules.items()}

    rows: list[dict] = []
    fields = infobox.get("fields") or {}

    for raw_field_name, field_data in fields.items():
        if not field_data:
            continue
        field_norm = _normalize_infobox_field_key(raw_field_name)
        mapping = norm_rules.get(field_norm)
        if not mapping:
            continue

        rel = mapping.get("rel")
        if not rel or rel not in valid_relations or rel == "RELATED_TO":
            continue

        raw_val = field_data.get("text") if isinstance(field_data, dict) else field_data
        if not raw_val:
            continue

        # Xử lý giá trị
        values: list[str] = []
        if isinstance(raw_val, list):
            values = [str(v).strip() for v in raw_val if str(v).strip()]
        else:
            # Tách dòng nếu có nhiều dòng xuống hàng
            lines = [line.strip() for line in str(raw_val).split("\n") if line.strip()]
            values = lines if lines else [str(raw_val).strip()]

        subj_type = mapping.get("subject", "page")
        obj_type = mapping.get("object", "value")

        for val in values:
            if not val or val == article_title:
                continue

            if subj_type == "value" and obj_type == "page":
                head = val
                tail = article_title
            else:
                head = article_title
                tail = val

            triplet = {
                "head": head,
                "relation": rel,
                "tail": tail,
                "start_year": start_year,
                "end_year": end_year,
                "year_target": "head" if head == article_title else "tail",
                "confidence": 0.95,
                "evidence": f"infobox:{raw_field_name}",
                "source": "infobox",
            }
            if article_id is not None:
                triplet["article_id"] = article_id
            if chunk_id is not None:
                triplet["chunk_id"] = chunk_id

            rows.append(triplet)

    return rows
