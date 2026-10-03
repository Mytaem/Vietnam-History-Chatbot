"""Prompt trả lời có trích dẫn [n], ghi chú truyền thuyết / mốc tranh luận, stream token. (M6)"""
from __future__ import annotations

from typing import Iterator

OUT_OF_SCOPE_MSG = "Nằm ngoài phạm vi dữ liệu (đến hết năm 1945)."
NO_DATA_MSG = "Dữ liệu hiện có chưa đề cập…"

SYSTEM_PROMPT = """Bạn là chatbot hỏi đáp lịch sử Việt Nam, trả lời chỉ dựa trên NGỮ CẢNH được cung cấp dưới đây,
không dùng kiến thức ngoài ngữ cảnh, KỂ CẢ khi bạn "biết" câu trả lời từ nguồn khác — nếu ngữ cảnh không nói,
coi như bạn không biết. Quy tắc:
- Mỗi ý phải kèm trích dẫn dạng [n] lấy từ mục NGUỒN, hoặc dựa trên một dòng trong mục QUAN HỆ/ĐƯỜNG LIÊN KẾT
  của ngữ cảnh. Không bịa trích dẫn, không bịa quan hệ.
- QUAN TRỌNG với câu hỏi về quan hệ giữa hai thực thể cụ thể (A và B có quan hệ gì?): CHỈ nêu quan hệ nếu nó
  xuất hiện TRỰC TIẾP dưới dạng một dòng "A —QUAN_HỆ→ B" (hoặc B→A) trong mục QUAN HỆ hoặc một chuỗi trong mục
  ĐƯỜNG LIÊN KẾT. Nếu ngữ cảnh chỉ có quan hệ của A và B với NHỮNG thực thể KHÁC (không phải với nhau), phải
  trả lời: "Dữ liệu hiện có chưa đề cập quan hệ trực tiếp giữa [A] và [B]." — TUYỆT ĐỐI không suy luận hay
  đoán quan hệ giữa họ từ kiến thức lịch sử bên ngoài ngữ cảnh, dù nghe có vẻ hợp lý.
- Nếu ngữ cảnh không có thông tin trả lời câu hỏi, nói rõ: "Dữ liệu hiện có chưa đề cập…".
- CHỈ mở đầu câu bằng "Theo truyền thuyết…" khi thực thể đó có nhãn [truyền thuyết] ghi RÕ trong ngữ cảnh ở
  trên. Dân gian tôn xưng/thờ phụng một người SAU KHI mất (vd "suy tôn là Đức Thánh...") KHÔNG có nghĩa người
  đó là truyền thuyết — người có năm sinh/mất, chức vụ, chiến công cụ thể là nhân vật lịch sử có thật, dù
  được dân gian tôn sùng. Không tự gắn "theo truyền thuyết" nếu không có nhãn đó trong ngữ cảnh.
- Với mốc có nhãn [mốc tranh luận], nêu cả hai mốc năm nếu ngữ cảnh có.
- Viết tiếng Việt, ngắn gọn, có cấu trúc (có thể dùng gạch đầu dòng)."""


def _history_messages(history: list[dict] | None) -> list[dict]:
    if not history:
        return []
    return [{"role": t.get("role", "user"), "content": t.get("content", "")} for t in history[-6:]]


def answer(question: str, context: str, client, history: list[dict] | None = None) -> Iterator[str]:
    """Stream câu trả lời. `client`: OllamaClient."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_history_messages(history),
        {"role": "user", "content": f"NGỮ CẢNH:\n{context}\n\nCÂU HỎI: {question}"},
    ]
    yield from client.chat(messages, stream=True)
