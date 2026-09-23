"""Pydantic schema cho output LLM - truyền JSON schema vào format= của Ollama. (M4)"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

EntityType = Literal["Person", "Event", "Place", "Polity", "Organization", "Work", "Culture"]
RelType = Literal[
    "CHILD_OF", "SPOUSE_OF", "MEMBER_OF", "BORN_IN", "DIED_IN", "RULED", "RULED_OVER",
    "SUCCEEDED", "FOUNDED", "CAPITAL_OF", "COMMANDED", "PARTICIPATED_IN", "OPPOSED",
    "OCCUPIED", "OCCURRED_AT", "PART_OF", "CAUSED", "LED_TO", "SIGNED", "AUTHORED",
    "FOUND_AT", "RELATED_TO",
]


class Entity(BaseModel):
    name: str = Field(description="Tên đầy đủ, phổ biến nhất, tiếng Việt có dấu")
    type: EntityType
    subtype: Optional[str] = None
    aliases: list[str] = []
    description: str = Field(description="1 câu mô tả dựa trên văn bản")
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class EntityOutput(BaseModel):
    entities: list[Entity]


class Triplet(BaseModel):
    head: str
    relation: RelType
    tail: str
    start_year: Optional[int] = None   # TCN là số âm
    end_year: Optional[int] = None
    role: Optional[str] = None
    side: Optional[str] = None
    evidence: str = Field(description="Trích NGUYÊN VĂN câu chứng minh từ đoạn văn")
    confidence: float = Field(ge=0, le=1)


class RelationOutput(BaseModel):
    triplets: list[Triplet]
