"""Prompt trích xuất entity / relation / gleaning + few-shot theo era. (M4)"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ONTOLOGY_PATH = PROJECT_ROOT / "configs" / "ontology.yaml"

PROMPT_VERSION = "v2"

ENTITY_SYSTEM = """Bạn là chuyên gia trích xuất tri thức lịch sử Việt Nam (từ tiền sử đến 1945).
Nhiệm vụ: Trích xuất danh sách thực thể lịch sử có trong đoạn văn theo đúng JSON schema.

Quy tắc bắt buộc:
1. CHỈ trích xuất thực thể được đề cập trực tiếp trong đoạn văn, tuyệt đối không suy diễn hay dùng kiến thức bên ngoài.
2. Gán type chính xác từ danh sách: Person, Event, Place, Polity, Organization, Work, Culture.
3. Bỏ qua mọi thực thể hoặc biến cố chỉ diễn ra sau năm 1945.
4. Đánh dấu legendary=true cho nhân vật, sự kiện hoặc địa danh thuộc thời kỳ truyền thuyết (Hùng Vương, An Dương Vương, Thánh Gióng...).
5. Tên thực thể phải chuẩn hóa tiếng Việt có dấu. Với sự kiện lịch sử nổi tiếng trùng tên khác năm (như các trận Bạch Đằng), bắt buộc gắn năm vào tên nếu văn bản đề cập (ví dụ: "Trận Bạch Đằng (938)", "Trận Bạch Đằng (1288)")."""

RELATION_SYSTEM = """Bạn là chuyên gia trích xuất quan hệ tri thức lịch sử Việt Nam (từ tiền sử đến 1945).
Nhiệm vụ: Trích xuất các quan hệ ngữ nghĩa giữa các thực thể đã được xác định từ Pass 1.

Quy tắc bắt buộc:
1. CHỈ tạo quan hệ giữa các thực thể có tên trong DANH SÁCH THỰC THỂ. Cả head và tail đều phải khớp chính xác tên từ danh sách này.
2. CHỈ sử dụng các quan hệ nằm trong danh sách QUAN HỆ HỢP LỆ được cung cấp, tuân thủ đúng chiều (Head → Tail) và ràng buộc kiểu thực thể.
3. Tuyệt đối không tạo quan hệ mơ hồ, không suy diễn ngoài đoạn văn.
4. Trường evidence BẮT BUỘC là câu hoặc cụm từ trích NGUYÊN VĂN từ đoạn văn làm bằng chứng trực tiếp.
5. Bỏ qua các sự kiện hoặc quan hệ diễn ra sau năm 1945."""

GLEANING_USER = """Hãy rà soát kỹ lại đoạn văn và danh sách đã trích xuất ở trên.
Nếu còn thực thể lịch sử quan trọng hoặc quan hệ trực tiếp nào bị bỏ sót trong đoạn văn, hãy bổ sung theo đúng quy tắc. Nếu không còn sót, trả về danh sách rỗng."""


def _load_ontology_definitions() -> dict[str, Any]:
    if not ONTOLOGY_PATH.exists():
        return {}
    return yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8")) or {}


# 5 bộ few-shot tiêu biểu cho 5 era: tiensu, dungnuoc, bacthuoc (kèm songsong), phongkien, candai
FEW_SHOT_BY_ERA: dict[str, list[dict[str, Any]]] = {
    "tiensu": [
        {
            "chunk": {
                "text": "Nền văn hóa Đông Sơn thuộc thời kỳ đồ đồng tại Việt Nam, phát triển rực rỡ tại vùng đồng bằng Bắc Bộ. Di chỉ khảo cổ học tiêu biểu được phát hiện tại di chỉ Đông Sơn bên bờ sông Mã thuộc tỉnh Thanh Hóa.",
                "header": "[Bài: Văn hóa Đông Sơn | Mục: Khảo cổ học]",
            },
            "entities": [
                {"name": "Văn hóa Đông Sơn", "type": "Culture", "description": "Nền văn hóa khảo cổ thời kỳ đồ đồng"},
                {"name": "Bắc Bộ", "type": "Place"},
                {"name": "di chỉ Đông Sơn", "type": "Place", "description": "Di chỉ khảo cổ học thời đồ đồng"},
                {"name": "sông Mã", "type": "Place"},
                {"name": "Thanh Hóa", "type": "Place"},
            ],
            "triplets": [
                {
                    "head": "Văn hóa Đông Sơn",
                    "relation": "FOUND_AT",
                    "tail": "di chỉ Đông Sơn",
                    "evidence": "Di chỉ khảo cổ học tiêu biểu được phát hiện tại di chỉ Đông Sơn",
                },
                {
                    "head": "di chỉ Đông Sơn",
                    "relation": "PART_OF",
                    "tail": "sông Mã",
                    "evidence": "di chỉ Đông Sơn bên bờ sông Mã",
                },
                {
                    "head": "di chỉ Đông Sơn",
                    "relation": "PART_OF",
                    "tail": "Thanh Hóa",
                    "evidence": "bên bờ sông Mã thuộc tỉnh Thanh Hóa",
                },
            ],
        }
    ],
    "dungnuoc": [
        {
            "chunk": {
                "text": "Thục Phán lên ngôi xưng là An Dương Vương, đổi quốc hiệu từ Văn Lang sang Âu Lạc vào năm 257 TCN. Vua cho xây dựng thành Cổ Loa làm kinh đô kiên cố để phòng thủ đất nước.",
                "header": "[Bài: An Dương Vương | Mục: Lập quốc]",
            },
            "entities": [
                {
                    "name": "An Dương Vương",
                    "type": "Person",
                    "legendary": True,
                    "start_year": -257,
                    "aliases": ["Thục Phán"],
                    "description": "Vua sáng lập nước Âu Lạc",
                },
                {"name": "Văn Lang", "type": "Polity", "legendary": True},
                {"name": "Âu Lạc", "type": "Polity", "legendary": True, "start_year": -257},
                {"name": "thành Cổ Loa", "type": "Place", "legendary": True},
            ],
            "triplets": [
                {
                    "head": "Âu Lạc",
                    "relation": "SUCCEEDED",
                    "tail": "Văn Lang",
                    "start_year": -257,
                    "evidence": "đổi quốc hiệu từ Văn Lang sang Âu Lạc vào năm 257 TCN",
                },
                {
                    "head": "An Dương Vương",
                    "relation": "RULED",
                    "tail": "Âu Lạc",
                    "start_year": -257,
                    "evidence": "Thục Phán lên ngôi xưng là An Dương Vương, đổi quốc hiệu từ Văn Lang sang Âu Lạc",
                },
                {
                    "head": "thành Cổ Loa",
                    "relation": "CAPITAL_OF",
                    "tail": "Âu Lạc",
                    "evidence": "xây dựng thành Cổ Loa làm kinh đô kiên cố",
                },
            ],
        }
    ],
    "bacthuoc": [
        {
            "chunk": {
                "text": "Mùa xuân năm 40, Trưng Trắc cùng Trưng Nhị dựng cờ khởi nghĩa chống lại thái thú Tô Định của nhà Đông Hán tại Mê Linh. Sau khi đánh đuổi thái thú Tô Định, Trưng Trắc xưng là Trưng Vương.",
                "header": "[Bài: Khởi nghĩa Hai Bà Trưng | Mục: Diễn biến]",
            },
            "entities": [
                {
                    "name": "Trưng Trắc",
                    "type": "Person",
                    "start_year": 40,
                    "aliases": ["Trưng Vương"],
                    "description": "Nữ thủ lĩnh khởi nghĩa chống Đông Hán",
                },
                {"name": "Trưng Nhị", "type": "Person", "start_year": 40},
                {
                    "name": "Khởi nghĩa Hai Bà Trưng",
                    "type": "Event",
                    "subtype": "Uprising",
                    "start_year": 40,
                },
                {"name": "Tô Định", "type": "Person", "description": "Thái thú Giao Chỉ thời Đông Hán"},
                {"name": "nhà Đông Hán", "type": "Polity"},
                {"name": "Mê Linh", "type": "Place"},
            ],
            "triplets": [
                {
                    "head": "Trưng Trắc",
                    "relation": "COMMANDED",
                    "tail": "Khởi nghĩa Hai Bà Trưng",
                    "start_year": 40,
                    "evidence": "Trưng Trắc cùng Trưng Nhị dựng cờ khởi nghĩa",
                },
                {
                    "head": "Trưng Trắc",
                    "relation": "OPPOSED",
                    "tail": "Tô Định",
                    "start_year": 40,
                    "evidence": "khởi nghĩa chống lại thái thú Tô Định",
                },
                {
                    "head": "Khởi nghĩa Hai Bà Trưng",
                    "relation": "OCCURRED_AT",
                    "tail": "Mê Linh",
                    "start_year": 40,
                    "evidence": "dựng cờ khởi nghĩa chống lại thái thú Tô Định của nhà Đông Hán tại Mê Linh",
                },
                {
                    "head": "Tô Định",
                    "relation": "MEMBER_OF",
                    "tail": "nhà Đông Hán",
                    "role": "thái thú",
                    "evidence": "thái thú Tô Định của nhà Đông Hán",
                },
            ],
        }
    ],
    "phongkien": [
        {
            "chunk": {
                "text": "Tháng 4 năm 1288, Hưng Đạo Đại vương Trần Quốc Tuấn chỉ huy quân dân Đại Việt đánh tan đạo thủy binh nhà Nguyên do Ô Mã Nhi cầm đầu trong Trận Bạch Đằng (1288) trên sông Bạch Đằng, kế thừa bài học thắng lợi từ Trận Bạch Đằng (938) của Ngô Quyền.",
                "header": "[Bài: Trận Bạch Đằng (1288) | Mục: Chiến sự]",
            },
            "entities": [
                {
                    "name": "Trần Quốc Tuấn",
                    "type": "Person",
                    "aliases": ["Hưng Đạo Đại vương"],
                    "description": "Tiết chế chỉ huy quân đội Đại Việt",
                },
                {"name": "Đại Việt", "type": "Polity"},
                {"name": "nhà Nguyên", "type": "Polity"},
                {"name": "Ô Mã Nhi", "type": "Person", "description": "Tướng thủy quân nhà Nguyên"},
                {
                    "name": "Trận Bạch Đằng (1288)",
                    "type": "Event",
                    "subtype": "Battle",
                    "start_year": 1288,
                    "end_year": 1288,
                },
                {"name": "sông Bạch Đằng", "type": "Place"},
                {
                    "name": "Trận Bạch Đằng (938)",
                    "type": "Event",
                    "subtype": "Battle",
                    "start_year": 938,
                    "end_year": 938,
                },
                {"name": "Ngô Quyền", "type": "Person", "start_year": 938},
            ],
            "triplets": [
                {
                    "head": "Trần Quốc Tuấn",
                    "relation": "COMMANDED",
                    "tail": "Trận Bạch Đằng (1288)",
                    "start_year": 1288,
                    "evidence": "Trần Quốc Tuấn chỉ huy quân dân Đại Việt đánh tan đạo thủy binh nhà Nguyên do Ô Mã Nhi cầm đầu trong Trận Bạch Đằng (1288)",
                },
                {
                    "head": "Ô Mã Nhi",
                    "relation": "COMMANDED",
                    "tail": "Trận Bạch Đằng (1288)",
                    "start_year": 1288,
                    "evidence": "đạo thủy binh nhà Nguyên do Ô Mã Nhi cầm đầu trong Trận Bạch Đằng (1288)",
                },
                {
                    "head": "Trận Bạch Đằng (1288)",
                    "relation": "OCCURRED_AT",
                    "tail": "sông Bạch Đằng",
                    "start_year": 1288,
                    "evidence": "Trận Bạch Đằng (1288) trên sông Bạch Đằng",
                },
                {
                    "head": "Đại Việt",
                    "relation": "OPPOSED",
                    "tail": "nhà Nguyên",
                    "evidence": "quân dân Đại Việt đánh tan đạo thủy binh nhà Nguyên",
                },
                {
                    "head": "Ngô Quyền",
                    "relation": "COMMANDED",
                    "tail": "Trận Bạch Đằng (938)",
                    "start_year": 938,
                    "evidence": "kế thừa bài học thắng lợi từ Trận Bạch Đằng (938) của Ngô Quyền",
                },
            ],
        }
    ],
    "candai": [
        {
            "chunk": {
                "text": "Ngày 3 tháng 2 năm 1930, Nguyễn Ái Quốc chủ trì hội nghị hợp nhất các tổ chức cộng sản để thành lập Đảng Cộng sản Việt Nam tại Cửu Long. Đến năm 1941, lãnh tụ Nguyễn Ái Quốc sáng lập mặt trận Việt Minh nhằm đoàn kết toàn dân chống phát xít Nhật và thực dân Pháp.",
                "header": "[Bài: Hồ Chí Minh | Mục: Hoạt động cách mạng]",
            },
            "entities": [
                {
                    "name": "Nguyễn Ái Quốc",
                    "type": "Person",
                    "aliases": ["Hồ Chí Minh"],
                    "description": "Lãnh tụ phong trào giải phóng dân tộc",
                },
                {"name": "Đảng Cộng sản Việt Nam", "type": "Organization", "start_year": 1930},
                {"name": "Cửu Long", "type": "Place"},
                {"name": "Việt Minh", "type": "Organization", "start_year": 1941},
                {"name": "Đế quốc Nhật Bản", "type": "Polity", "aliases": ["phát xít Nhật"]},
                {"name": "Pháp", "type": "Polity", "aliases": ["thực dân Pháp"]},
            ],
            "triplets": [
                {
                    "head": "Nguyễn Ái Quốc",
                    "relation": "FOUNDED",
                    "tail": "Đảng Cộng sản Việt Nam",
                    "start_year": 1930,
                    "evidence": "Nguyễn Ái Quốc chủ trì hội nghị hợp nhất các tổ chức cộng sản để thành lập Đảng Cộng sản Việt Nam tại Cửu Long",
                },
                {
                    "head": "Nguyễn Ái Quốc",
                    "relation": "FOUNDED",
                    "tail": "Việt Minh",
                    "start_year": 1941,
                    "evidence": "lãnh tụ Nguyễn Ái Quốc sáng lập mặt trận Việt Minh",
                },
                {
                    "head": "Việt Minh",
                    "relation": "OPPOSED",
                    "tail": "Đế quốc Nhật Bản",
                    "evidence": "mặt trận Việt Minh nhằm đoàn kết toàn dân chống phát xít Nhật",
                },
                {
                    "head": "Việt Minh",
                    "relation": "OPPOSED",
                    "tail": "Pháp",
                    "evidence": "chống phát xít Nhật và thực dân Pháp",
                },
            ],
        }
    ],
}

# Hỗ trợ bí danh cho nhánh songsong
FEW_SHOT_BY_ERA["songsong"] = FEW_SHOT_BY_ERA["bacthuoc"]


def _format_context_hints(period: dict | None) -> str:
    """Tạo gợi ý ngữ cảnh ngắn gọn từ thông tin period."""
    if not period:
        return ""
    lines = []
    period_name = period.get("name")
    if period_name:
        lines.append(f"Giai đoạn lịch sử: {period_name}")
    roles = period.get("role_vocab")
    if roles:
        lines.append(f"Thuật ngữ/chức danh thường gặp: {', '.join(roles[:8])}")
    polities = period.get("polities")
    if polities:
        lines.append(f"Chính thể/thế lực tiêu biểu: {', '.join(polities[:6])}")
    return "\n".join(lines)


def build_entity_messages(chunk: dict, period: dict | None = None) -> list[dict[str, str]]:
    """Tạo messages cho Pass 1 (Trích xuất thực thể)."""
    messages: list[dict[str, str]] = [{"role": "system", "content": ENTITY_SYSTEM}]

    # Lấy few-shot theo era
    era_id = (period or {}).get("era_id") or chunk.get("era_id") or "phongkien"
    examples = FEW_SHOT_BY_ERA.get(era_id) or FEW_SHOT_BY_ERA["phongkien"]

    for ex in examples[:1]:
        ex_chunk = ex["chunk"]
        ex_user = f"Đoạn văn:\n{ex_chunk['text']}"
        if ex_chunk.get("header"):
            ex_user = f"{ex_chunk['header']}\n{ex_user}"
        messages.append({"role": "user", "content": ex_user})
        messages.append({
            "role": "assistant",
            "content": json.dumps({"entities": ex["entities"]}, ensure_ascii=False),
        })

    # Xây dựng prompt người dùng
    user_parts = []
    header = chunk.get("header") or ""
    if not header and chunk.get("page_title"):
        header = f"[Bài: {chunk.get('page_title')} | Mục: {chunk.get('section_path', '')}]"
    if header:
        user_parts.append(header)

    hints = _format_context_hints(period)
    if hints:
        user_parts.append(hints)

    # Gợi ý wikilink nếu có
    raw_links = chunk.get("links") or []
    link_targets = []
    for lnk in raw_links:
        t = lnk if isinstance(lnk, str) else lnk.get("target")
        if t and t not in link_targets:
            link_targets.append(t)
    if link_targets:
        user_parts.append(f"Liên kết có trong đoạn: {', '.join(link_targets[:10])}")

    chunk_text = chunk.get("text") or ""
    user_parts.append(f"Đoạn văn:\n{chunk_text}")

    messages.append({"role": "user", "content": "\n\n".join(user_parts)})
    return messages


def _filter_applicable_relations(present_types: set[str], ontology_defs: dict[str, Any]) -> list[str]:
    """Lọc các quan hệ có domain và range khả thi với các type thực thể hiện có, giúp prompt siêu ngắn."""
    relations_cfg = ontology_defs.get("relations", {})
    applicable = []

    for rel_name, rel_info in relations_cfg.items():
        domains = set(rel_info.get("domain", []))
        ranges = set(rel_info.get("range", []))
        # Nếu domain và range đều có thể khớp với các type đang có
        if (domains & present_types or "*" in domains) and (ranges & present_types or "*" in ranges):
            dom_str = "/".join(sorted(domains & present_types or domains))
            rng_str = "/".join(sorted(ranges & present_types or ranges))
            applicable.append(f"- {rel_name}: ({dom_str}) -[:{rel_name}]-> ({rng_str})")

    return applicable


def build_relation_messages(chunk: dict, entities: list[dict], period: dict | None = None) -> list[dict[str, str]]:
    """Tạo messages cho Pass 2 (Trích xuất quan hệ)."""
    messages: list[dict[str, str]] = [{"role": "system", "content": RELATION_SYSTEM}]

    # Lấy few-shot theo era
    era_id = (period or {}).get("era_id") or chunk.get("era_id") or "phongkien"
    examples = FEW_SHOT_BY_ERA.get(era_id) or FEW_SHOT_BY_ERA["phongkien"]

    for ex in examples[:1]:
        ex_chunk = ex["chunk"]
        ex_ent_list = [f"- {e['name']} ({e['type']})" for e in ex["entities"]]
        ex_user = f"Đoạn văn:\n{ex_chunk['text']}\n\nDANH SÁCH THỰC THỂ:\n" + "\n".join(ex_ent_list)
        messages.append({"role": "user", "content": ex_user})
        messages.append({
            "role": "assistant",
            "content": json.dumps({"triplets": ex["triplets"]}, ensure_ascii=False),
        })

    # Xác định tập type hiện có để rút gọn quan hệ
    present_types = set()
    entity_lines = []
    for ent in entities:
        name = ent.get("name") if isinstance(ent, dict) else getattr(ent, "name", "")
        etype = ent.get("type") if isinstance(ent, dict) else getattr(ent, "type", "")
        etype_str = str(etype.value if hasattr(etype, "value") else etype)
        if name and etype_str:
            present_types.add(etype_str)
            entity_lines.append(f"- {name} ({etype_str})")

    ontology_defs = _load_ontology_definitions()
    applicable_rels = _filter_applicable_relations(present_types, ontology_defs)

    user_parts = []
    chunk_text = chunk.get("text") or ""
    user_parts.append(f"Đoạn văn:\n{chunk_text}")

    if entity_lines:
        user_parts.append("DANH SÁCH THỰC THỂ (CHỈ ĐƯỢC TẠO QUAN HỆ GIỮA CÁC THỰC THỂ NÀY):\n" + "\n".join(entity_lines))

    if applicable_rels:
        user_parts.append("QUAN HỆ HỢP LỆ (TUÂN THỦ ĐÚNG CHIỀU VÀ KIỂU):\n" + "\n".join(applicable_rels))

    hints = _format_context_hints(period)
    if hints:
        user_parts.append(hints)

    messages.append({"role": "user", "content": "\n\n".join(user_parts)})
    return messages
