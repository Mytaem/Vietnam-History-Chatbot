"""Client Ollama: chat, chat_json (ép JSON schema), embed; retry + đếm token. (M1)"""
from __future__ import annotations

from typing import Iterator, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class OllamaClient:
    def __init__(self, host: str, chat_model: str, embed_model: str, num_ctx: int = 8192):
        self.host = host
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.num_ctx = num_ctx

    def chat(self, messages: list[dict], stream: bool = False) -> str | Iterator[str]:
        raise NotImplementedError

    def chat_json(self, messages: list[dict], schema: type[T]) -> T:
        """Gọi với format=<json schema>, temperature=0; retry khi parse lỗi."""
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        raise NotImplementedError
