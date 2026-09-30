"""Pydantic schema cho output LLM - truyền JSON schema vào format= của Ollama. (M4)"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ONTOLOGY_PATH = PROJECT_ROOT / "configs" / "ontology.yaml"


def _load_ontology_enums() -> tuple[list[str], list[str]]:
    """Đọc configs/ontology.yaml để sinh enum động."""
    if not ONTOLOGY_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy ontology tại: {ONTOLOGY_PATH}")
    data = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8")) or {}
    types = list(data.get("entity_types", {}).keys())
    rels = list(data.get("relations", {}).keys())
    if not types or not rels:
        raise ValueError(f"Ontology không hợp lệ tại {ONTOLOGY_PATH}")
    return types, rels


_entity_types, _rel_types = _load_ontology_enums()

# Sinh enum động kiểu (str, Enum) từ ontology.yaml, hỗ trợ __args__ cho loader.py
EntityType = Enum("EntityType", {k: k for k in _entity_types}, type=str)
RelType = Enum("RelType", {k: k for k in _rel_types}, type=str)

# Gắn __args__ tương thích ngược với typing.Literal (cho loader.py: allowed_types = set(RelType.__args__))
EntityType.__args__ = tuple(_entity_types)
RelType.__args__ = tuple(_rel_types)


class Entity(BaseModel):
    name: str = Field(description="Tên đầy đủ, phổ biến nhất, tiếng Việt có dấu")
    type: EntityType = Field(description="Loại thực thể thuộc ontology")
    subtype: Optional[str] = Field(default=None, description="Phân loại con (Battle, War, Uprising, Treaty, Reform, Movement, Coup, Founding)")
    aliases: list[str] = Field(default_factory=list, description="Các tên gọi khác, tên húy, bí danh")
    description: Optional[str] = Field(default=None, description="1 câu mô tả ngắn gọn vai trò dựa trên văn bản")
    start_year: Optional[int] = Field(default=None, description="Năm bắt đầu hoặc năm sinh (TCN là số âm)")
    end_year: Optional[int] = Field(default=None, description="Năm kết thúc hoặc năm mất (TCN là số âm)")
    legendary: Optional[bool] = Field(default=False, description="True nếu là nhân vật/sự kiện thời hồng hoang, truyền thuyết")
    wikilink: Optional[str] = Field(default=None, description="Tiêu đề wikilink tương ứng nếu có trong đoạn")
    qid: Optional[str] = Field(default=None, description="Mã Wikidata QID nếu có")


class EntityOutput(BaseModel):
    entities: list[Entity] = Field(default_factory=list)


class Triplet(BaseModel):
    head: str = Field(description="Tên thực thể chủ thể (phải thuộc danh sách thực thể từ Pass 1)")
    relation: RelType = Field(description="Loại quan hệ thuộc ontology")
    tail: str = Field(description="Tên thực thể đối tượng (phải thuộc danh sách thực thể từ Pass 1)")
    evidence: str = Field(description="Câu hoặc cụm từ trích NGUYÊN VĂN từ đoạn văn làm bằng chứng")
    start_year: Optional[int] = Field(default=None, description="Năm bắt đầu của quan hệ nếu có (TCN là số âm)")
    end_year: Optional[int] = Field(default=None, description="Năm kết thúc của quan hệ nếu có")
    role: Optional[str] = Field(default=None, description="Vai trò tùy chọn (ví dụ: thái thú, tướng quân...)")
    side: Optional[str] = Field(default=None, description="Phe/bên tham gia tùy chọn")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Độ tin cậy trích xuất")


class RelationOutput(BaseModel):
    triplets: list[Triplet] = Field(default_factory=list)
