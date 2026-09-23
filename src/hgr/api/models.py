"""Request/response schemas cho FastAPI. (M7)"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    history: list[dict] = []
    period_filter: Optional[tuple[int, int]] = None
    mode: Literal["graphrag", "vector"] = "graphrag"


class Citation(BaseModel):
    n: int
    title: str
    section: str
    url: str
    quote: str
