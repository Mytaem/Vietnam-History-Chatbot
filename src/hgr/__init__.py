"""hgr - History GraphRAG: chatbot lịch sử Việt Nam (tiền sử → 1945), 100% local LLM."""
import sys

# Console Windows mặc định dùng cp1252/cp437, không hiển thị được tiếng Việt có dấu.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

__version__ = "0.1.0"
