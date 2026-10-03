"""Client Ollama: chat, chat_json (ép JSON schema), embed; retry + đếm token. (M1)"""
from __future__ import annotations

import time
from typing import Any, Callable, Iterator, TypeVar

import httpx
import ollama
from ollama import ResponseError
from pydantic import BaseModel, ValidationError

from hgr.log import get_logger

T = TypeVar("T", bound=BaseModel)

log = get_logger(__name__)

# Danh sách các ngoại lệ mạng và vận chuyển cần retry:
# - httpx.TimeoutException: bao gồm ReadTimeout, WriteTimeout, ConnectTimeout, PoolTimeout (theo MRO)
# - httpx.NetworkError: bao gồm ReadError, WriteError, ConnectError, CloseError (theo MRO)
# - httpx.RemoteProtocolError: lỗi vi phạm protocol từ phía server (Ollama server crash, OOM, reset kết nối)
# - ConnectionError: ngoại lệ built-in ném ra bởi ollama.Client khi gặp ConnectError
# Không bắt httpx.TransportError chung chung vì sẽ nuốt cả LocalProtocolError và UnsupportedProtocol (lỗi phía client)
RETRYABLE_NETWORK_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    ConnectionError,
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
        keep_alive: str | float | None = None,
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

        if keep_alive is None:
            try:
                from hgr.config import get_settings
                llm_cfg = get_settings().llm
                keep_alive = llm_cfg.get("keep_alive") if isinstance(llm_cfg, dict) else getattr(llm_cfg, "keep_alive", None)
            except Exception:
                keep_alive = None

        self.timeout_s = float(timeout_s)
        self.backoff_factor = float(backoff_factor)
        self.keep_alive = keep_alive
        # Truyền timeout_s trực tiếp vào ollama.Client để cấu hình timeout cho httpx client bên dưới
        self._client = ollama.Client(host=host, timeout=self.timeout_s)

    def _warn_if_near_ctx(self, response) -> None:
        used = (response.prompt_eval_count or 0) + (response.eval_count or 0)
        if used and used > 0.9 * self.num_ctx:
            log.warning("Dùng %d/%d token (>90%% num_ctx), prompt có thể đã bị cắt", used, self.num_ctx)

    def _execute_with_retry(
        self,
        call_fn: Callable[[], Any],
        validate_fn: Callable[[Any], Any] | None = None,
        action_name: str = "call",
    ) -> Any:
        """Hàm nội bộ dùng chung: thực thi call_fn với retry backoff cho chat, chat_json và embed.

        Phân loại lỗi chặt chẽ:
        - 400 <= status_code < 500 (như 404 model not found): ném ngay, không retry.
        - status_code >= 500 hoặc -1: lỗi server Ollama, retry có backoff.
        - RETRYABLE_NETWORK_EXCEPTIONS: retry có backoff.
        - ValidationError: retry khi validate_fn kiểm tra schema lỗi.
        """
        total_attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, total_attempts + 1):
            try:
                result = call_fn()
                if validate_fn is not None:
                    return validate_fn(result)
                return result
            except ResponseError as e:
                # Lỗi phía client không thể khắc phục -> ném ngay, gọi đúng 1 lần
                if 400 <= e.status_code < 500:
                    log.error("Lỗi client từ Ollama khi %s (status %d): %s - không thể retry", action_name, e.status_code, e)
                    raise
                last_error = e
                log.warning(
                    "Lỗi server Ollama khi %s (lần %d/%d, status %d): %s",
                    action_name,
                    attempt,
                    total_attempts,
                    e.status_code,
                    e,
                )
            except RETRYABLE_NETWORK_EXCEPTIONS as e:
                last_error = e
                log.warning(
                    "Lỗi kết nối/timeout Ollama khi %s (lần %d/%d): %s: %s",
                    action_name,
                    attempt,
                    total_attempts,
                    type(e).__name__,
                    e,
                )
            except ValidationError as e:
                last_error = e
                log.warning(
                    "%s parse lỗi (lần %d/%d): %s",
                    action_name,
                    attempt,
                    total_attempts,
                    e,
                )

            if attempt < total_attempts and self.backoff_factor > 0:
                time.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        # Ném ngoại lệ tường minh tương ứng sau khi hết lượt retry
        if isinstance(last_error, httpx.TimeoutException):
            raise TimeoutError(f"{action_name} timeout sau {total_attempts} lần: {last_error}") from last_error
        elif isinstance(last_error, (ConnectionError, httpx.NetworkError)):
            raise ConnectionError(f"{action_name} mất kết nối sau {total_attempts} lần: {last_error}") from last_error
        elif isinstance(last_error, ResponseError):
            raise last_error
        elif isinstance(last_error, ValidationError):
            raise ValueError(f"{action_name} thất bại sau {total_attempts} lần: {last_error}") from last_error
        elif last_error is not None:
            raise last_error
        else:
            raise RuntimeError(f"{action_name} thất bại sau {total_attempts} lần")

    def chat(self, messages: list[dict], stream: bool = False) -> str | Iterator[str]:
        options = {"num_ctx": self.num_ctx, "temperature": self.temperature}
        kwargs: dict[str, Any] = {
            "model": self.chat_model,
            "messages": messages,
            "options": options,
        }
        if self.keep_alive is not None:
            kwargs["keep_alive"] = self.keep_alive

        if stream:
            def _iter() -> Iterator[str]:
                for chunk in self._client.chat(stream=True, **kwargs):
                    yield chunk.message.content or ""

            return _iter()

        def _call_and_process():
            resp = self._client.chat(stream=False, **kwargs)
            self._warn_if_near_ctx(resp)
            return resp.message.content or ""

        return self._execute_with_retry(_call_and_process, action_name="chat")

    def chat_json(self, messages: list[dict], schema: type[T]) -> T:
        """Gọi với format=<json schema>, temperature=0; retry có backoff khi parse lỗi hoặc gặp sự cố mạng/timeout."""
        options = {"num_ctx": self.num_ctx, "temperature": 0.0}
        kwargs: dict[str, Any] = {
            "model": self.chat_model,
            "messages": messages,
            "format": schema.model_json_schema(),
            "options": options,
        }
        if self.keep_alive is not None:
            kwargs["keep_alive"] = self.keep_alive

        def _call():
            return self._client.chat(**kwargs)

        def _validate(response):
            self._warn_if_near_ctx(response)
            content = response.message.content or ""
            return schema.model_validate_json(content)

        return self._execute_with_retry(_call, validate_fn=_validate, action_name="chat_json")

    def embed(self, texts: list[str]) -> list[list[float]]:
        kwargs: dict[str, Any] = {
            "model": self.embed_model,
            "input": texts,
        }
        if self.keep_alive is not None:
            kwargs["keep_alive"] = self.keep_alive

        def _call():
            return self._client.embed(**kwargs)

        response = self._execute_with_retry(_call, action_name="embed")
        return [list(vec) for vec in response.embeddings]

    def list_models(self) -> list[str]:
        response = self._client.list()
        return [m.model for m in response.models if m.model]
