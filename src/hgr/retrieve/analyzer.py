"""LLM phân tích câu hỏi → QueryPlan. (M6)"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

Intent = Literal["factoid", "multihop", "temporal", "relational", "comparison", "overview"]


class QueryPlan(BaseModel):
    intent: Intent
    entities: list[str] = []
    rel_hints: list[str] = []
    rewritten: str
    time_range: Optional[tuple[int, int]] = None
    periods: list[str] = []


SYSTEM_PROMPT = """Bạn phân tích câu hỏi lịch sử Việt Nam (tiền sử đến hết 1945) để chuẩn bị truy hồi dữ liệu.
Trả về JSON đúng schema với các trường:
- intent: một trong factoid (hỏi 1 sự kiện/thực thể), multihop (cần nhiều bước suy luận qua các thực thể),
  temporal (hỏi theo mốc/khoảng thời gian), relational (hỏi quan hệ giữa 2 thực thể, "A và B"),
  comparison (so sánh 2+ thực thể), overview (tổng quan một giai đoạn/chủ đề rộng).
- entities: tên riêng (người, sự kiện, địa danh, triều đại...) được nhắc trong câu, giữ nguyên tiếng Việt có dấu.
- rel_hints: tên quan hệ có thể liên quan nếu đoán được (ví dụ CHILD_OF, RULED, PARTICIPATED_IN, OPPOSED...), để trống nếu không rõ.
- rewritten: viết lại câu hỏi đầy đủ, giải đại từ ("ông ấy", "trận đó"...) dựa theo lịch sử hội thoại, không đổi ý nghĩa.
- time_range, periods: để trống [] / null, một bước luật riêng sẽ tính các trường này.
Chỉ dựa vào câu hỏi và lịch sử hội thoại được cung cấp, không suy diễn thêm sự kiện ngoài câu hỏi."""


def _history_text(history: list[dict]) -> str:
    if not history:
        return "(không có)"
    lines = []
    for turn in history[-6:]:
        role = "Người dùng" if turn.get("role") == "user" else "Trợ lý"
        lines.append(f"{role}: {turn.get('content', '')}")
    return "\n".join(lines)


def analyze(question: str, history: list[dict], client) -> QueryPlan:
    """`client`: OllamaClient. Luôn trả về QueryPlan hợp lệ (fallback factoid nếu LLM lỗi)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Lịch sử hội thoại:\n{_history_text(history)}\n\nCâu hỏi: {question}"},
    ]
    try:
        return client.chat_json(messages, QueryPlan)
    except Exception:
        return QueryPlan(intent="factoid", entities=[], rel_hints=[], rewritten=question)
