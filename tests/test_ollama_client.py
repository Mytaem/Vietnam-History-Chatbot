"""Test đơn vị cho OllamaClient: mock network/timeout, retry backoff, RemoteProtocolError và embed."""
from __future__ import annotations

from unittest.mock import MagicMock
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


def _mock_embed_response(vectors: list[list[float]]):
    mock_resp = MagicMock()
    mock_resp.embeddings = vectors
    return mock_resp


def test_timeout_first_attempt_succeeds_second():
    """Timeout lần 1 rồi thành công lần 2: chat_json trả kết quả đúng, số lần gọi đúng (2 lần)."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,
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

    assert client._client.chat.call_count == 3


def test_remote_protocol_error_retried_successfully():
    """RemoteProtocolError lần 1 rồi thành công lần 2: retry đúng."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,
    )

    valid_json = '{"name": "Trần Nhân Tông", "year": 1293}'
    client._client.chat = MagicMock(
        side_effect=[
            httpx.RemoteProtocolError("Server disconnected prematurely"),
            _mock_chat_response(valid_json),
        ]
    )

    res = client.chat_json([{"role": "user", "content": "hi"}], SimpleSchema)
    assert res.name == "Trần Nhân Tông"
    assert res.year == 1293
    assert client._client.chat.call_count == 2


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


def test_embed_timeout_retried_successfully():
    """embed() gặp timeout rồi thành công: retry đúng."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,
    )

    client._client.embed = MagicMock(
        side_effect=[
            httpx.ReadTimeout("Embed request timed out"),
            _mock_embed_response([[0.1, 0.2, 0.3]]),
        ]
    )

    res = client.embed(["Khởi nghĩa Lam Sơn"])
    assert res == [[0.1, 0.2, 0.3]]
    assert client._client.embed.call_count == 2


def test_embed_404_raises_immediately():
    """embed() lỗi 404 thì ném ngay, gọi một lần."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="nonexistent-embed",
        max_retries=2,
        backoff_factor=0.0,
    )

    client._client.embed = MagicMock(
        side_effect=ResponseError("model 'nonexistent-embed' not found", status_code=404)
    )

    with pytest.raises(ResponseError) as exc_info:
        client.embed(["Đoạn văn mẫu"])

    assert exc_info.value.status_code == 404
    assert client._client.embed.call_count == 1


def test_chat_retried_on_network_error():
    """chat() stream=False cũng dùng chung cơ chế retry khi gặp lỗi mạng."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        max_retries=2,
        backoff_factor=0.0,
    )

    client._client.chat = MagicMock(
        side_effect=[
            ConnectionError("Connection lost to Ollama"),
            _mock_chat_response("Câu trả lời thành công"),
        ]
    )

    text = client.chat([{"role": "user", "content": "hello"}], stream=False)
    assert text == "Câu trả lời thành công"
    assert client._client.chat.call_count == 2


def test_client_initialization_passes_timeout_and_keep_alive():
    """Kiểm tra OllamaClient truyền đúng timeout_s và keep_alive vào client bên dưới."""
    client = OllamaClient(
        host="http://localhost:11434",
        chat_model="test-model",
        embed_model="test-embed",
        timeout_s=60.0,
        keep_alive="10m",
    )
    assert client.timeout_s == 60.0
    assert client.keep_alive == "10m"
    assert client._client._client.timeout.read == 60.0

    # Kiểm tra keep_alive được truyền vào lệnh gọi chat và embed
    client._client.chat = MagicMock(return_value=_mock_chat_response("ok"))
    client.chat([{"role": "user", "content": "hi"}])
    assert client._client.chat.call_args.kwargs.get("keep_alive") == "10m"

    client._client.embed = MagicMock(return_value=_mock_embed_response([[1.0]]))
    client.embed(["hi"])
    assert client._client.embed.call_args.kwargs.get("keep_alive") == "10m"
