"""Prompt trả lời có trích dẫn [n], ghi chú truyền thuyết / mốc tranh luận, stream token. (M6)"""
from __future__ import annotations

from typing import Iterator

OUT_OF_SCOPE_MSG = "Nằm ngoài phạm vi dữ liệu (đến hết năm 1945)."
NO_DATA_MSG = "Dữ liệu hiện có chưa đề cập…"


def answer(question: str, context: str, history: list[dict] | None = None) -> Iterator[str]:
    raise NotImplementedError
