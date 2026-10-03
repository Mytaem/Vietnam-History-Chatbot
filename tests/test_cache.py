"""Test đơn vị cho DiskCache: ghi nguyên tử, đọc an toàn khi hỏng, và sinh khóa băm ổn định."""
from __future__ import annotations

from pathlib import Path
import unicodedata
from unittest.mock import patch

from hgr.llm.cache import DiskCache, make_cache_key


def test_cache_set_and_get_success(tmp_path: Path):
    """Cache: ghi rồi đọc lại khớp."""
    cache = DiskCache(tmp_path)
    data = {"entities": ["Lý Thường Kiệt", "Như Nguyệt"], "score": 0.95}

    cache.set("k1", data)
    loaded = cache.get("k1")

    assert loaded == data


def test_cache_miss_on_corrupt_or_empty_file(tmp_path: Path):
    """Đọc cache: file JSON hỏng hoặc rỗng coi như không có (miss - trả về None) chứ không văng lỗi."""
    cache = DiskCache(tmp_path)

    # 1. File không tồn tại
    assert cache.get("nonexistent") is None

    # 2. File JSON bị hỏng cú pháp (ngắt giữa chừng)
    bad_file = tmp_path / "bad.json"
    bad_file.write_text('{"incomplete": true, "key":', encoding="utf-8")
    assert cache.get("bad") is None

    # 3. File rỗng 0 bytes
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("", encoding="utf-8")
    assert cache.get("empty") is None

    # 4. File chỉ chứa khoảng trắng và xuống dòng
    spaces_file = tmp_path / "spaces.json"
    spaces_file.write_text("   \n\t  ", encoding="utf-8")
    assert cache.get("spaces") is None


def test_atomic_write_cleans_temp_file_on_error(tmp_path: Path):
    """Giả lập lỗi giữa lúc ghi (ném exception trước os.replace):

    - Không để lại file đích hỏng
    - Dọn sạch file tạm trong thư mục
    """
    cache = DiskCache(tmp_path)
    target_file = tmp_path / "test_fail.json"

    # Giả lập lỗi ở bước os.replace
    with patch("os.replace", side_effect=OSError("Disk write simulated failure")):
        try:
            cache.set("test_fail", {"val": 123})
        except OSError:
            pass

    # File đích không được tạo hoặc không bị hỏng
    assert not target_file.exists()

    # Thư mục không còn file tạm .tmp nào còn sót lại
    tmp_files = list(tmp_path.glob("*.tmp")) + list(tmp_path.glob(".*.tmp"))
    assert len(tmp_files) == 0


def test_make_cache_key_avoids_ambiguity():
    """Hai bộ tham số ghép nhập nhằng (ví dụ ('a', 'bc') và ('ab', 'c')) phải cho hai khóa khác nhau."""
    k1 = make_cache_key("a", "bc", "chk_1", "text")
    k2 = make_cache_key("ab", "c", "chk_1", "text")
    assert k1 != k2

    # Nhập nhằng giữa chunk_id và nội dung
    k3 = make_cache_key("qwen", "v1", "chk_1", "2_content")
    k4 = make_cache_key("qwen", "v1", "chk_12", "_content")
    assert k3 != k4


def test_make_cache_key_nfc_nfd_equivalence():
    """Cùng đầu vào (kể cả khác dạng tổ hợp NFD và dựng sẵn NFC) phải cho cùng một khóa."""
    # Chuỗi tiếng Việt có dấu dạng dựng sẵn NFC
    text_nfc = unicodedata.normalize("NFC", "Trần Hưng Đạo lãnh đạo nhân dân đánh bại quân Nguyên Mông")
    # Chuỗi tiếng Việt có dấu dạng tổ hợp NFD
    text_nfd = unicodedata.normalize("NFD", "Trần Hưng Đạo lãnh đạo nhân dân đánh bại quân Nguyên Mông")

    # Bản thân hai chuỗi này khác nhau về số lượng ký tự và byte code
    assert text_nfc != text_nfd

    # Khi đưa vào make_cache_key, kết quả phải ra cùng một mã băm sha256
    k_nfc = make_cache_key("qwen3:4b", "v1", "chunk_101", text_nfc)
    k_nfd = make_cache_key("qwen3:4b", "v1", "chunk_101", text_nfd)
    assert k_nfc == k_nfd


def test_cache_key_generation_stability_and_uniqueness():
    """Hai khóa khác nhau khi đổi phiên bản prompt hoặc nội dung chunk, và cùng khóa khi đầu vào giống hệt."""
    k_base = make_cache_key("qwen3:4b", "v1", "chunk_101", "Trận Bạch Đằng diễn ra năm 938.")

    # Cùng đầu vào -> cùng khóa
    k_same = make_cache_key("qwen3:4b", "v1", "chunk_101", "Trận Bạch Đằng diễn ra năm 938.")
    assert k_base == k_same

    # Khác prompt_version
    k_diff_prompt = make_cache_key("qwen3:4b", "v2", "chunk_101", "Trận Bạch Đằng diễn ra năm 938.")
    assert k_base != k_diff_prompt

    # Khác nội dung chunk
    k_diff_text = make_cache_key("qwen3:4b", "v1", "chunk_101", "Trận Như Nguyệt diễn ra năm 1077.")
    assert k_base != k_diff_text

    # Khác model
    k_diff_model = make_cache_key("qwen2.5:3b", "v1", "chunk_101", "Trận Bạch Đằng diễn ra năm 938.")
    assert k_base != k_diff_model

    # Khác chunk_id
    k_diff_chunk_id = make_cache_key("qwen3:4b", "v1", "chunk_102", "Trận Bạch Đằng diễn ra năm 938.")
    assert k_base != k_diff_chunk_id

    # Đảm bảo phương thức static make_key trên DiskCache hoạt động tương đương
    assert DiskCache.make_key("qwen3:4b", "v1", "chunk_101", "Trận Bạch Đằng diễn ra năm 938.") == k_base


def test_legacy_diskcache_key_api_preserved():
    """Giữ nguyên API hiện có của DiskCache.key(*parts)."""
    legacy_k1 = DiskCache.key("a", "b", "c")
    legacy_k2 = DiskCache.key("a", "b", "c")
    legacy_k3 = DiskCache.key("a", "b", "d")

    assert isinstance(legacy_k1, str)
    assert len(legacy_k1) == 40  # sha1
    assert legacy_k1 == legacy_k2
    assert legacy_k1 != legacy_k3
