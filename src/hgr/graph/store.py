"""Neo4jStore: kết nối, chạy Cypher, upsert theo lô, lấy subgraph. (M1)"""
from __future__ import annotations

from typing import Any


class Neo4jStore:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri, self.user, self.password, self.database = uri, user, password, database
        self._driver = None

    def ping(self) -> bool:
        raise NotImplementedError

    def run(self, cypher: str, **params: Any) -> list[dict]:
        raise NotImplementedError

    def run_batches(self, cypher: str, rows: list[dict], batch_size: int = 500) -> None:
        raise NotImplementedError

    def apply_schema(self, path: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
