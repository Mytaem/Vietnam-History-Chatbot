"""Embed Chunk.text và Entity (display_name: description) bằng bge-m3 → vector index. (M5)"""
from __future__ import annotations

import json
from pathlib import Path

from hgr.config import get_settings


def _embed_file(store, client, path: Path, label: str, text_for_row, batch_size: int) -> int:
    if not path.exists():
        return 0
    count = 0
    batch = []
    texts = []

    def flush() -> None:
        nonlocal count, batch, texts
        if not batch:
            return
        vectors = client.embed(texts)
        if len(vectors) != len(batch):
            raise ValueError(f"Embedding trả {len(vectors)} vector cho {len(batch)} record")
        store.run_batches(
            f"UNWIND $rows AS row MATCH (n:{label} {{id: row.id}}) SET n.embedding = row.embedding",
            [{"id": row["id"], "embedding": vector} for row, vector in zip(batch, vectors)],
        )
        count += len(batch)
        batch = []
        texts = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            text = text_for_row(row).strip()
            if not text:
                continue
            batch.append(row)
            texts.append(text)
            if len(batch) >= batch_size:
                flush()
    flush()
    return count

def embed_chunks(store, client, batch_size: int = 32) -> int:
    if store is None or client is None:
        return 0
    settings = get_settings()
    path = Path(settings.project_root) / settings.paths.data_dir / "processed" / "chunks.jsonl"
    return _embed_file(
        store,
        client,
        path,
        "Chunk",
        lambda row: f"{row.get('header', '')}\n{row.get('text', '')}",
        batch_size,
    )


def embed_entities(store, client, batch_size: int = 32) -> int:
    if store is None or client is None:
        return 0
    settings = get_settings()
    path = Path(settings.project_root) / settings.paths.data_dir / "resolved" / "entities.jsonl"
    return _embed_file(
        store,
        client,
        path,
        "Entity",
        lambda row: f"{row.get('name', '')}\n{row.get('description', '')}",
        batch_size,
    )
