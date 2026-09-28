"""Test đơn vị cho OllamaClient: mock network/timeout, retry backoff, và error handling."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import httpx
import pytest
from ollama import ResponseError
from pydantic import BaseModel

from hgr.llm.ollama_client import OllamaClient


class SimpleSchema(BaseModel):
    name: str
    year: int


def _mock_chat_response(content: str):
    mock_resp = MagicMock()
    mock_resp.message.content = content
    mock_resp.prompt_eval_count = 10
    mock_resp.eval_count = 20
    return mock_resp


def test_timeout_first_attempt_succeeds_second():
    """Timeout lần 1 rồi thành công lần 2: chat_json trả kết quả đúng, số lần gọi đúng (2 lần)."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,  # Không delay trong test
    )

    valid_json = '{"name": "Lý Thường Kiệt", "year": 1077}'
    client._client.chat = MagicMock(
        side_effect=[
            httpx.ReadTimeout("Request timed out"),
            _mock_chat_response(valid_json),
        ]
    )

    res = client.chat_json([{"role": "user", "content": "hi"}], SimpleSchema)
    assert res.name == "Lý Thường Kiệt"
    assert res.year == 1077
    assert client._client.chat.call_count == 2


def test_consecutive_timeouts_fail_after_max_retries():
    """Timeout liên tiếp vượt số lần cho phép: ném lỗi rõ ràng, không lặp vô hạn."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,
    )

    client._client.chat = MagicMock(
        side_effect=httpx.ReadTimeout("Always timed out")
    )

    with pytest.raises(TimeoutError, match="chat_json timeout sau 3 lần"):
        client.chat_json([{"role": "user", "content": "hi"}], SimpleSchema)

    # 1 lần đầu + 2 lần retry = 3 lần gọi
    assert client._client.chat.call_count == 3


def test_non_retryable_error_raises_immediately():
    """Lỗi không retry được (như model không tồn tại - HTTP 404): ném ngay, chỉ gọi đúng một lần."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="nonexistent-model",
        embed_model="test-embed",
        max_retries=3,
        backoff_factor=0.0,
    )

    client._client.chat = MagicMock(
        side_effect=ResponseError("model 'nonexistent-model' not found", status_code=404)
    )

    with pytest.raises(ResponseError) as exc_info:
        client.chat_json([{"role": "user", "content": "hi"}], SimpleSchema)

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value)
    # Chỉ gọi đúng 1 lần, không hề retry
    assert client._client.chat.call_count == 1


def test_invalid_json_then_valid_json_succeeds():
    """JSON sai rồi đúng: hành vi retry parse cũ vẫn hoạt động tốt."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,
    )

    invalid_json = '{"name": "Trần Hưng Đạo", "year": "not_an_int"}'
    valid_json = '{"name": "Trần Hưng Đạo", "year": 1288}'

    client._client.chat = MagicMock(
        side_effect=[
            _mock_chat_response(invalid_json),
            _mock_chat_response(valid_json),
        ]
    )

    res = client.chat_json([{"role": "user", "content": "hi"}], SimpleSchema)
    assert res.name == "Trần Hưng Đạo"
    assert res.year == 1288
    assert client._client.chat.call_count == 2


def test_server_error_500_retried():
    """Lỗi server 500 được retry và thành công ở lần sau."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,
    )

    valid_json = '{"name": "Quang Trung", "year": 1789}'
    client._client.chat = MagicMock(
        side_effect=[
            ResponseError("Internal server error", status_code=500),
            _mock_chat_response(valid_json),
        ]
    )

    res = client.chat_json([{"role": "user", "content": "hi"}], SimpleSchema)
    assert res.name == "Quang Trung"
    assert res.year == 1789
    assert client._client.chat.call_count == 2


def test_client_initialization_passes_timeout():
    """Kiểm tra OllamaClient truyền đúng timeout_s vào client bên dưới."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        timeout_s=60.0,
    )
    assert client.timeout_s == 60.0
    # Client ollama bọc httpx.Client với timeout tương ứng
    assert client._client._client.timeout.read == 60.0
