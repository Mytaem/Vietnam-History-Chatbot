"""Neo4jStore: kết nối, chạy Cypher, upsert theo lô, lấy subgraph. (M1)"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from hgr.log import get_logger

log = get_logger(__name__)


class Neo4jStore:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri, self.user, self.password, self.database = uri, user, password, database
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def ping(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            log.warning("Không kết nối được Neo4j tại %s: %s", self.uri, e)
            return False

    def run(self, cypher: str, **params: Any) -> list[dict]:
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]

    def run_batches(self, cypher: str, rows: list[dict], batch_size: int = 500) -> None:
        """`cypher` nhận tham số `$rows` (dùng UNWIND $rows AS row ...)."""
        with self._driver.session(database=self.database) as session:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                session.run(cypher, rows=batch)

    def apply_schema(self, path: str) -> None:
        statements = [s.strip() for s in Path(path).read_text(encoding="utf-8").split(";") if s.strip()]
        with self._driver.session(database=self.database) as session:
            for statement in statements:
                session.run(statement)

    def close(self) -> None:
        self._driver.close()
