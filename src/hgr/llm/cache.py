"""Cache đĩa cho kết quả LLM theo sha1/sha256(prompt_version + input) → resume được. (M4)"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any
import unicodedata
import uuid

from hgr.log import get_logger

log = get_logger(__name__)


def make_cache_key(
    model: str,
    prompt_version: str,
    chunk_id: str,
    chunk_content: str,
) -> str:
    """Tạo khóa cache ổn định từ (model, phiên bản prompt, chunk_id, nội dung chunk) bằng sha256.

    Chuẩn hóa Unicode NFC cho tất cả các thành phần để tránh lệch mã do gõ phím khác nhau (NFC vs NFD),
    và đóng gói định dạng mảng JSON để tránh hiện tượng trùng lặp ranh giới ("a", "bc") vs ("ab", "c").
    """
    model_norm = unicodedata.normalize("NFC", str(model or "")).strip()
    prompt_norm = unicodedata.normalize("NFC", str(prompt_version or "")).strip()
    chunk_id_norm = unicodedata.normalize("NFC", str(chunk_id or "")).strip()
    content_norm = unicodedata.normalize("NFC", str(chunk_content or "")).strip()

    raw = json.dumps([model_norm, prompt_norm, chunk_id_norm, content_norm], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DiskCache:
    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(*parts: str) -> str:
        """API cũ: sha1 các phần tử nối bằng separator."""
        return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def make_key(
        model: str,
        prompt_version: str,
        chunk_id: str,
        chunk_content: str,
    ) -> str:
        """Tạo khóa cache ổn định từ (model, prompt_version, chunk_id, chunk_content)."""
        return make_cache_key(model, prompt_version, chunk_id, chunk_content)

    def get(self, key: str) -> Any | None:
        """Đọc cache: file không tồn tại, rỗng hoặc hỏng thì trả về None (miss) chứ không văng lỗi."""
        path = self.dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return None
            return json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cache file %s bị hỏng hoặc không đọc được (%s), coi như cache miss", path, e)
            return None

    def set(self, key: str, value: Any) -> None:
        """Ghi nguyên tử: ghi vào file tạm có uuid trong cùng thư mục, rồi os.replace sang file đích."""
        target_path = self.dir / f"{key}.json"
        temp_path = self.dir / f".{key}.{uuid.uuid4().hex}.tmp"
        try:
            temp_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            os.replace(temp_path, target_path)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise
