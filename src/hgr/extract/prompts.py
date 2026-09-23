"""Prompt trích xuất entity / relation / gleaning + few-shot theo era. (M4)"""

PROMPT_VERSION = "v1"

ENTITY_SYSTEM = """TODO(M4): prompt trích xuất thực thể (PLAN.md Mục 6.2 bước 4b)."""
RELATION_SYSTEM = """TODO(M4): prompt trích xuất quan hệ, chỉ dùng thực thể từ ENTITY LIST."""
GLEANING_USER = """TODO(M4): hỏi lại các thực thể/quan hệ bị bỏ sót."""

# 5 bộ few-shot: tiensu, dungnuoc, bacthuoc (+ songsong), phongkien, candai
FEW_SHOT_BY_ERA: dict[str, list[dict]] = {}


def build_entity_messages(chunk: dict, period: dict) -> list[dict]:
    raise NotImplementedError


def build_relation_messages(chunk: dict, entities: list[dict], period: dict) -> list[dict]:
    raise NotImplementedError
