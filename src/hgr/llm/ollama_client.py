"""Client Ollama: chat, chat_json (ép JSON schema), embed; retry + đếm token. (M1)"""
from __future__ import annotations

from typing import Iterator, TypeVar

import ollama
from pydantic import BaseModel, ValidationError

from hgr.log import get_logger

T = TypeVar("T", bound=BaseModel)

log = get_logger(__name__)


class OllamaClient:
    def __init__(
        self,
        host: str,
        chat_model: str,
        embed_model: str,
        num_ctx: int = 8192,
        temperature: float = 0.0,
        max_retries: int = 2,
    ):
        self.host = host
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.max_retries = max_retries
        self._client = ollama.Client(host=host)

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
        """Gọi với format=<json schema>, temperature=0; retry khi parse lỗi."""
        options = {"num_ctx": self.num_ctx, "temperature": 0.0}
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            response = self._client.chat(
                model=self.chat_model,
                messages=messages,
                format=schema.model_json_schema(),
                options=options,
            )
            self._warn_if_near_ctx(response)
            content = response.message.content or ""
            try:
                return schema.model_validate_json(content)
            except ValidationError as e:
                last_error = e
                log.warning("chat_json parse lỗi (lần %d/%d): %s", attempt, self.max_retries + 1, e)
        raise ValueError(f"chat_json thất bại sau {self.max_retries + 1} lần: {last_error}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embed(model=self.embed_model, input=texts)
        return [list(vec) for vec in response.embeddings]

    def list_models(self) -> list[str]:
        response = self._client.list()
        return [m.model for m in response.models if m.model]
