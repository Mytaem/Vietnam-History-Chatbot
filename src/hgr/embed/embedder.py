"""Embed Chunk.text và Entity (display_name: description) bằng bge-m3 → vector index. (M5)"""
from __future__ import annotations


def embed_chunks(store, client, batch_size: int = 32) -> int:
    raise NotImplementedError


def embed_entities(store, client, batch_size: int = 32) -> int:
    raise NotImplementedError
