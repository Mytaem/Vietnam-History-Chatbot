"""Client Ollama: chat, chat_json (ép JSON schema), embed; retry + đếm token. (M1)"""
from __future__ import annotations

import time
from typing import Iterator, TypeVar

import httpx
import ollama
from ollama import ResponseError
from pydantic import BaseModel, ValidationError

from hgr.log import get_logger

T = TypeVar("T", bound=BaseModel)

log = get_logger(__name__)

# Danh sách các ngoại lệ mạng và timeout cụ thể được kiểm chứng trên httpx và ollama
RETRYABLE_NETWORK_EXCEPTIONS = (
    httpx.TimeoutException,
    ConnectionError,
    httpx.ConnectError,
    httpx.NetworkError,
)


class OllamaClient:
    def __init__(
        self,
        host: str,
        chat_model: str,
        embed_model: str,
        num_ctx: int = 8192,
        temperature: float = 0.0,
        max_retries: int = 2,
        timeout_s: float | int | None = None,
        backoff_factor: float = 1.0,
    ):
        self.host = host
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.max_retries = max_retries

        if timeout_s is None:
            try:
                from hgr.config import get_settings
                timeout_s = float(get_settings().llm.timeout_s)
            except Exception:
                timeout_s = 120.0

        self.timeout_s = float(timeout_s)
        self.backoff_factor = float(backoff_factor)
        # Truyền timeout_s trực tiếp vào ollama.Client để cấu hình timeout cho httpx client bên dưới
        self._client = ollama.Client(host=host, timeout=self.timeout_s)

    def _warn_if_near_ctx(self, response) -> None:
        used = (response.prompt_eval_count or 0) + (response.eval_count or 0)
        if used and used > 0.9 * self.num_ctx:
            log.warning("Dùng %d/%d token (>90%% num_ctx), prompt có thể đã bị cắt", used, self.num_ctx)

    def chat(self, messages: list[dict], stream: bool = False) -> str | Iterator[str]:
        options = {"num_ctx": self.num_ctx, "temperature": self.temperature}
        if stream:
            def _iter() -> Iterator[str]:
                for chunk in self._client.chat(
                    model=self.chat_model, messages=messages, stream=True, options=options
                ):
                    yield chunk.message.content or ""

            return _iter()

        response = self._client.chat(model=self.chat_model, messages=messages, stream=False, options=options)
        self._warn_if_near_ctx(response)
        return response.message.content or ""

    def chat_json(self, messages: list[dict], schema: type[T]) -> T:
        """Gọi với format=<json schema>, temperature=0; retry có backoff khi parse lỗi hoặc gặp sự cố mạng/timeout."""
        options = {"num_ctx": self.num_ctx, "temperature": 0.0}
        last_error: Exception | None = None
        total_attempts = self.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            try:
                response = self._client.chat(
                    model=self.chat_model,
                    messages=messages,
                    format=schema.model_json_schema(),
                    options=options,
                )
            except ResponseError as e:
                # Lỗi phía client không thể khắc phục (ví dụ 404 model chưa pull, 400 bad request) -> không retry
                if 400 <= e.status_code < 500:
                    log.error("Lỗi client từ Ollama (status %d): %s - không thể retry", e.status_code, e)
                    raise
                # Lỗi phía server (5xx hoặc -1) -> thử lại
                last_error = e
                log.warning(
                    "Lỗi server Ollama (lần %d/%d, status %d): %s",
                    attempt,
                    total_attempts,
                    e.status_code,
                    e,
                )
                if attempt < total_attempts and self.backoff_factor > 0:
                    time.sleep(self.backoff_factor * (2 ** (attempt - 1)))
                continue
            except RETRYABLE_NETWORK_EXCEPTIONS as e:
                last_error = e
                log.warning(
                    "Lỗi kết nối/timeout Ollama (lần %d/%d): %s: %s",
                    attempt,
                    total_attempts,
                    type(e).__name__,
                    e,
                )
                if attempt < total_attempts and self.backoff_factor > 0:
                    time.sleep(self.backoff_factor * (2 ** (attempt - 1)))
                continue

            self._warn_if_near_ctx(response)
            content = response.message.content or ""
            try:
                return schema.model_validate_json(content)
            except ValidationError as e:
                last_error = e
                log.warning(
                    "chat_json parse lỗi (lần %d/%d): %s",
                    attempt,
                    total_attempts,
                    e,
                )
                if attempt < total_attempts and self.backoff_factor > 0:
                    time.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        # Ném ngoại lệ tường minh tương ứng sau khi hết lượt retry
        if isinstance(last_error, httpx.TimeoutException):
            raise TimeoutError(f"chat_json timeout sau {total_attempts} lần: {last_error}") from last_error
        elif isinstance(last_error, (ConnectionError, httpx.ConnectError, httpx.NetworkError)):
            raise ConnectionError(f"chat_json mất kết nối sau {total_attempts} lần: {last_error}") from last_error
        elif isinstance(last_error, ResponseError):
            raise last_error
        elif isinstance(last_error, ValidationError):
            raise ValueError(f"chat_json thất bại sau {total_attempts} lần: {last_error}") from last_error
        elif last_error is not None:
            raise last_error
        else:
            raise RuntimeError(f"chat_json thất bại sau {total_attempts} lần")

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embed(model=self.embed_model, input=texts)
        return [list(vec) for vec in response.embeddings]

    def list_models(self) -> list[str]:
        response = self._client.list()
        return [m.model for m in response.models if m.model]
