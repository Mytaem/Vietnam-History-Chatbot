"""Focused checks for M5 graph loading contracts."""
import json

from hgr.graph.loader import load_periods, load_resolved
from hgr.periods import Era, Period


class FakeStore:
    def __init__(self):
        self.batches = []
        self.queries = []

    def run_batches(self, query, rows, batch_size=500):
        self.batches.append((query, rows))

    def run(self, query, **params):
        self.queries.append((query, params))


def test_load_periods_creates_hierarchy_and_mainline_order():
    first = Period("first", "First", "era", 1, 10)
    parallel = Period("parallel", "Parallel", "era", 3, 7, parallel=True)
    second = Period("second", "Second", "era", 11, 20)
    era = Era("era", "Era", 1, 20, "#fff", periods=[first, parallel, second])
    store = FakeStore()

    load_periods(store, [era])

    query_text = "\n".join(query for query, _ in store.batches)
    assert "PART_OF" in query_text
    next_rows = [rows for query, rows in store.batches if "NEXT" in query and "Period" in query]
    assert next_rows == [[{"from": "first", "to": "second"}]]


def test_load_resolved_creates_nodes_and_typed_edges(tmp_path):
    entities = [
        {"id": "local:a", "name": "A", "aliases": ["A"], "type": "Person"},
        {"id": "local:b", "name": "B", "aliases": ["B"], "type": "Polity"},
    ]
    relations = [{
        "id": "rel:a:b",
        "head_id": "local:a",
        "tail_id": "local:b",
        "relation": "RULED",
        "confidence": 1.0,
        "evidence": "A ruled B",
    }]
    (tmp_path / "entities.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in entities), encoding="utf-8"
    )
    (tmp_path / "relations.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in relations), encoding="utf-8"
    )
    store = FakeStore()

    load_resolved(store, str(tmp_path))

    assert any("MERGE (e:Entity" in query for query, _ in store.batches)
    rel_query, rel_rows = next(
        (query, rows) for query, rows in store.batches if "apoc.merge.relationship" in query
    )
    assert "row.type" in rel_query
    assert rel_rows[0]["type"] == "RULED"
    assert rel_rows[0]["props"]["id"] == "rel:a:b"