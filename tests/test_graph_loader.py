"""Focused checks for M5 graph loading contracts & real Neo4j integration."""
from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest

from hgr.config import get_settings
from hgr.graph.loader import (
    check_apoc,
    compute_degree_and_display_names,
    link_periods,
    load_articles_chunks,
    load_periods,
    load_resolved,
)
from hgr.graph.store import Neo4jStore
from hgr.periods import Era, Period
from hgr.resolve.resolver import run as run_resolver


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


# ==============================================================================
# INTEGRATION TESTS VỚI NEO4J THẬT (TỰ DỌN DẸP SẠCH SẼ 100% SAU MỖI TEST)
# ==============================================================================

@pytest.fixture
def neo4j_ctx():
    settings = get_settings()
    uri = settings.neo4j.uri
    uris_to_try = [uri]
    if "localhost" in uri:
        uris_to_try.append(uri.replace("localhost", "127.0.0.1"))

    store = None
    for u in uris_to_try:
        candidate = Neo4jStore(
            uri=u,
            user=settings.neo4j.user,
            password=settings.neo4j.password,
            database=settings.neo4j.database,
        )
        if candidate.ping():
            store = candidate
            break
        candidate.close()

    if store is None:
        pytest.skip(f"Neo4j không khả dụng tại {settings.neo4j.uri}")

    run_id = f"test_{uuid.uuid4().hex[:8]}"
    tracked_ids: list[str | int] = []

    class TestContext:
        def __init__(self, store, run_id, tracked_ids):
            self.store = store
            self.run_id = run_id
            self.prefix = f"test:{run_id}"
            self.tracked_ids = tracked_ids

        def make_id(self, suffix: str) -> str:
            eid = f"{self.prefix}:{suffix}"
            self.tracked_ids.append(eid)
            return eid

        def track(self, *ids):
            for i in ids:
                if i and i not in self.tracked_ids:
                    self.tracked_ids.append(i)
            return ids[0] if ids else None

    ctx = TestContext(store, run_id, tracked_ids)
    try:
        yield ctx
    finally:
        # TEARDOWN: Xóa triệt để mọi node / relationship tạo ra trong test run này
        if tracked_ids:
            store.run(
                "MATCH (n) WHERE n.id IN $ids OR n.page_id IN $ids DETACH DELETE n",
                ids=tracked_ids,
            )
        store.run(
            "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
            prefix=ctx.prefix,
        )
        store.close()


def test_apoc_version_check(neo4j_ctx):
    """Xác nhận APOC hoạt động thật và trả về version."""
    version = check_apoc(neo4j_ctx.store)
    assert version != ""
    assert isinstance(version, str)


def test_mentions_direction_chunk_to_entity(neo4j_ctx, tmp_path):
    """Yêu cầu 1: (Chunk)-[:MENTIONS]->(Entity) đúng 1, chiều ngược lại bằng 0."""
    store = neo4j_ctx.store
    ent_id = neo4j_ctx.make_id("thang_long")
    chunk_id = neo4j_ctx.make_id("chunk_001")
    page_id = int(uuid.uuid4().int % 1000000)
    neo4j_ctx.track(page_id)
    ent_name = f"Thăng Long {neo4j_ctx.run_id}"

    # 1. Tạo Entity
    store.run(
        "MERGE (e:Entity {id: $id, name: $name, type: 'Place'})",
        id=ent_id, name=ent_name,
    )

    # 2. Tạo dữ liệu processed/articles.jsonl và processed/chunks.jsonl
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    article_data = [{"page_id": page_id, "title": "Hà Nội", "qid": "Q1858"}]
    chunk_data = [{
        "id": chunk_id,
        "page_id": page_id,
        "links": [{"target": ent_name, "entity_id": ent_id}],
        "text": f"Kinh đô {ent_name} thành lập năm 1010.",
    }]
    (proc_dir / "articles.jsonl").write_text(
        "\n".join(json.dumps(a) for a in article_data), encoding="utf-8"
    )
    (proc_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(c) for c in chunk_data), encoding="utf-8"
    )

    load_articles_chunks(store, str(tmp_path))

    # Kiểm tra chiều Chunk -> Entity có đúng 1 cạnh
    fwd = store.run(
        "MATCH (c:Chunk {id: $cid})-[:MENTIONS]->(e:Entity {id: $eid}) RETURN count(*) AS cnt",
        cid=chunk_id, eid=ent_id,
    )[0]["cnt"]
    assert fwd == 1

    # Kiểm tra chiều Entity -> Chunk KHÔNG tồn tại (phải bằng 0)
    rev = store.run(
        "MATCH (e:Entity {id: $eid})-[:MENTIONS]->(c:Chunk {id: $cid}) RETURN count(*) AS cnt",
        cid=chunk_id, eid=ent_id,
    )[0]["cnt"]
    assert rev == 0


def test_mentions_uses_resolved_id_not_confused_by_same_name(neo4j_ctx, tmp_path):
    """Yêu cầu 4: Hai Entity CÙNG TÊN GỐC nhưng khác id (3 trận Bạch Đằng),
    mỗi Chunk có entity_id rõ ràng -> chỉ MENTIONS đúng Entity tương ứng."""
    store = neo4j_ctx.store
    e1_id = neo4j_ctx.make_id("bach_dang_938")
    e2_id = neo4j_ctx.make_id("bach_dang_1288")
    c1_id = neo4j_ctx.make_id("chunk_938")
    c2_id = neo4j_ctx.make_id("chunk_1288")
    p1_id = int(uuid.uuid4().int % 1000000)
    p2_id = int(uuid.uuid4().int % 1000000) + 1
    neo4j_ctx.track(p1_id, p2_id)

    shared_name = f"Trận Bạch Đằng {neo4j_ctx.run_id}"

    # 1. Dựng 2 Entity CÙNG TÊN GỐC nhưng khác ID và năm
    store.run(
        "MERGE (e:Entity {id: $id, name: $name, type: 'Event', start_year: 938})",
        id=e1_id, name=shared_name,
    )
    store.run(
        "MERGE (e:Entity {id: $id, name: $name, type: 'Event', start_year: 1288})",
        id=e2_id, name=shared_name,
    )

    # 2. Hai Chunk khác nhau, mỗi chunk có entity_id đã được resolve tương ứng
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    article_data = [
        {"page_id": p1_id, "title": "Ngô Quyền"},
        {"page_id": p2_id, "title": "Trần Hưng Đạo"},
    ]
    chunk_data = [
        {
            "id": c1_id,
            "page_id": p1_id,
            "links": [{"target": shared_name, "entity_id": e1_id}],
            "text": "Ngô Quyền đánh bại quân Nam Hán trên sông Bạch Đằng năm 938.",
        },
        {
            "id": c2_id,
            "page_id": p2_id,
            "links": [{"target": shared_name, "entity_id": e2_id}],
            "text": "Trần Hưng Đạo tiêu diệt quân Ô Mã Nhi trên sông Bạch Đằng năm 1288.",
        },
    ]
    (proc_dir / "articles.jsonl").write_text(
        "\n".join(json.dumps(a) for a in article_data), encoding="utf-8"
    )
    (proc_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(c) for c in chunk_data), encoding="utf-8"
    )

    load_articles_chunks(store, str(tmp_path))

    # Khẳng định Chunk 1 chỉ MENTIONS Entity 1 (938), không dính Entity 2 (1288)
    c1_to_e1 = store.run(
        "MATCH (c:Chunk {id: $cid})-[:MENTIONS]->(e:Entity {id: $eid}) RETURN count(*) AS cnt",
        cid=c1_id, eid=e1_id,
    )[0]["cnt"]
    c1_to_e2 = store.run(
        "MATCH (c:Chunk {id: $cid})-[:MENTIONS]->(e:Entity {id: $eid}) RETURN count(*) AS cnt",
        cid=c1_id, eid=e2_id,
    )[0]["cnt"]
    assert c1_to_e1 == 1
    assert c1_to_e2 == 0

    # Khẳng định Chunk 2 chỉ MENTIONS Entity 2 (1288), không dính Entity 1 (938)
    c2_to_e2 = store.run(
        "MATCH (c:Chunk {id: $cid})-[:MENTIONS]->(e:Entity {id: $eid}) RETURN count(*) AS cnt",
        cid=c2_id, eid=e2_id,
    )[0]["cnt"]
    c2_to_e1 = store.run(
        "MATCH (c:Chunk {id: $cid})-[:MENTIONS]->(e:Entity {id: $eid}) RETURN count(*) AS cnt",
        cid=c2_id, eid=e1_id,
    )[0]["cnt"]
    assert c2_to_e2 == 1
    assert c2_to_e1 == 0



def test_entity_secondary_label_person(neo4j_ctx, tmp_path):
    """Yêu cầu 2: Node Entity có nhãn phụ Person qua APOC."""
    store = neo4j_ctx.store
    ent_id = neo4j_ctx.make_id("ngo_quyen")

    entities = [{
        "id": ent_id,
        "name": f"Ngô Quyền {neo4j_ctx.run_id}",
        "type": "Person",
        "start_year": 898,
        "end_year": 944,
    }]
    (tmp_path / "entities.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entities), encoding="utf-8"
    )

    load_resolved(store, str(tmp_path))

    records = store.run(
        "MATCH (p:Person {id: $id}) RETURN labels(p) AS l",
        id=ent_id,
    )
    assert len(records) == 1
    labels = records[0]["l"]
    assert "Entity" in labels
    assert "Person" in labels


def test_in_period_year_overlap_and_single_source_of_truth(neo4j_ctx):
    """Yêu cầu 3: IN_PERIOD theo overlap năm. Entity lệch năm không được nối dù có period_ids cũ."""
    store = neo4j_ctx.store
    period_id = neo4j_ctx.make_id("nha_tran")
    e1_id = neo4j_ctx.make_id("tran_thai_tong")
    e2_id = neo4j_ctx.make_id("tran_nhan_tong")
    e3_id = neo4j_ctx.make_id("ly_thai_to")

    # Tạo Period: Nhà Trần (1225 - 1400)
    store.run(
        "MERGE (p:Period {id: $id, name: 'Nhà Trần', start: 1225, end: 1400})",
        id=period_id,
    )
    # Entity 1: 1225 - 1258 (nằm trong period)
    store.run(
        "MERGE (e:Entity {id: $id, name: 'Trần Thái Tông', start_year: 1225, end_year: 1258})",
        id=e1_id,
    )
    # Entity 2: 1278 - 1293 (nằm trong period)
    store.run(
        "MERGE (e:Entity {id: $id, name: 'Trần Nhân Tông', start_year: 1278, end_year: 1293})",
        id=e2_id,
    )
    # Entity 3: 1009 - 1028 (lệch hoàn toàn khỏi Nhà Trần, nhưng period_ids ghi nha_tran)
    store.run(
        "MERGE (e:Entity {id: $id, name: 'Lý Thái Tổ', start_year: 1009, end_year: 1028, period_ids: [$pid]})",
        id=e3_id, pid=period_id,
    )
    # Entity 4: Không có start_year (Địa danh/Văn hóa không rõ năm) -> dùng fallback qua period_ids
    e4_id = neo4j_ctx.make_id("thanh_nha_ho")
    store.run(
        "MERGE (e:Entity {id: $id, name: 'Thành Nhà Hồ', period_ids: [$pid]})",
        id=e4_id, pid=period_id,
    )

    link_periods(store)

    c1 = store.run(
        "MATCH (e:Entity {id: $eid})-[:IN_PERIOD]->(p:Period {id: $pid}) RETURN count(*) AS cnt",
        eid=e1_id, pid=period_id,
    )[0]["cnt"]
    assert c1 == 1

    c2 = store.run(
        "MATCH (e:Entity {id: $eid})-[:IN_PERIOD]->(p:Period {id: $pid}) RETURN count(*) AS cnt",
        eid=e2_id, pid=period_id,
    )[0]["cnt"]
    assert c2 == 1

    # Overlap năm là nguồn sự thật: Lý Thái Tổ KHÔNG có cạnh tới Nhà Trần
    c3 = store.run(
        "MATCH (e:Entity {id: $eid})-[:IN_PERIOD]->(p:Period {id: $pid}) RETURN count(*) AS cnt",
        eid=e3_id, pid=period_id,
    )[0]["cnt"]
    assert c3 == 0

    # Fallback qua period_ids cho entity không có start_year: Thành Nhà Hồ CÓ cạnh tới Nhà Trần
    c4 = store.run(
        "MATCH (e:Entity {id: $eid})-[:IN_PERIOD]->(p:Period {id: $pid}) RETURN count(*) AS cnt",
        eid=e4_id, pid=period_id,
    )[0]["cnt"]
    assert c4 == 1



def test_display_name_disambiguation_with_year(neo4j_ctx):
    """Yêu cầu 4: Entity trùng name có start_year -> 'Tên (năm)', không trùng -> 'Tên'."""
    store = neo4j_ctx.store
    e1_id = neo4j_ctx.make_id("bach_dang_938")
    e2_id = neo4j_ctx.make_id("bach_dang_1288")
    e3_id = neo4j_ctx.make_id("chi_lang_1427")

    shared_name = f"Trận Bạch Đằng {neo4j_ctx.run_id}"
    unique_name = f"Trận Chi Lăng {neo4j_ctx.run_id}"

    store.run(
        "MERGE (e:Entity {id: $id, name: $name, start_year: 938})",
        id=e1_id, name=shared_name,
    )
    store.run(
        "MERGE (e:Entity {id: $id, name: $name, start_year: 1288})",
        id=e2_id, name=shared_name,
    )
    store.run(
        "MERGE (e:Entity {id: $id, name: $name, start_year: 1427})",
        id=e3_id, name=unique_name,
    )

    compute_degree_and_display_names(store)

    d1 = store.run("MATCH (e:Entity {id: $id}) RETURN e.display_name AS d", id=e1_id)[0]["d"]
    d2 = store.run("MATCH (e:Entity {id: $id}) RETURN e.display_name AS d", id=e2_id)[0]["d"]
    d3 = store.run("MATCH (e:Entity {id: $id}) RETURN e.display_name AS d", id=e3_id)[0]["d"]

    assert d1 == f"{shared_name} (938)"
    assert d2 == f"{shared_name} (1288)"
    assert d3 == unique_name


def test_evidence_chunk_ids_accumulation(neo4j_ctx, tmp_path):
    """Yêu cầu 5: Nạp quan hệ COMMANDED từ 2 chunk -> evidence_chunk_ids chứa cả 2, không trùng."""
    store = neo4j_ctx.store
    head_id = neo4j_ctx.make_id("tran_hung_dao")
    tail_id = neo4j_ctx.make_id("bach_dang_1288")

    # Tạo 2 Entity trước
    store.run("MERGE (e:Entity {id: $id, name: 'Trần Hưng Đạo', type: 'Person'})", id=head_id)
    store.run("MERGE (e:Entity {id: $id, name: 'Trận Bạch Đằng 1288', type: 'Event'})", id=tail_id)

    # Lần 1: nạp từ chunk-1
    rel1 = [{
        "id": f"rel:{head_id}:COMMANDED:{tail_id}",
        "head_id": head_id,
        "tail_id": tail_id,
        "relation": "COMMANDED",
        "evidence_chunk_ids": ["chunk-1"],
        "confidence": 0.9,
    }]
    (tmp_path / "relations.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rel1), encoding="utf-8"
    )
    load_resolved(store, str(tmp_path))

    # Lần 2: nạp cùng quan hệ từ chunk-2 (và lặp lại chunk-1)
    rel2 = [{
        "id": f"rel:{head_id}:COMMANDED:{tail_id}",
        "head_id": head_id,
        "tail_id": tail_id,
        "relation": "COMMANDED",
        "evidence_chunk_ids": ["chunk-2", "chunk-1"],
        "confidence": 0.95,
    }]
    (tmp_path / "relations.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rel2), encoding="utf-8"
    )
    load_resolved(store, str(tmp_path))

    records = store.run(
        "MATCH (a:Entity {id: $hid})-[r:COMMANDED]->(b:Entity {id: $tid}) "
        "RETURN r.evidence_chunk_ids AS chunks",
        hid=head_id, tid=tail_id,
    )
    assert len(records) == 1
    chunks = records[0]["chunks"]
    assert set(chunks) == {"chunk-1", "chunk-2"}
    assert len(chunks) == 2


def test_invalid_relation_rejected_and_logged(neo4j_ctx, tmp_path):
    """Yêu cầu 6: Quan hệ ngoài ontology bị từ chối, không nạp Neo4j, ghi vào loader_rejects.jsonl."""
    store = neo4j_ctx.store
    head_id = neo4j_ctx.make_id("head_a")
    tail_id = neo4j_ctx.make_id("tail_b")

    store.run("MERGE (e:Entity {id: $id, name: 'A'})", id=head_id)
    store.run("MERGE (e:Entity {id: $id, name: 'B'})", id=tail_id)

    invalid_rel = [{
        "id": f"rel:{head_id}:FAKE_RELATION_XYZ:{tail_id}",
        "head_id": head_id,
        "tail_id": tail_id,
        "relation": "FAKE_RELATION_XYZ",
        "confidence": 0.5,
    }]
    (tmp_path / "relations.jsonl").write_text(
        "\n".join(json.dumps(r) for r in invalid_rel), encoding="utf-8"
    )

    load_resolved(store, str(tmp_path))

    # Kiểm tra không có cạnh nào được tạo trong Neo4j
    edges = store.run(
        "MATCH (a:Entity {id: $hid})-[r]->(b:Entity {id: $tid}) RETURN type(r) AS t",
        hid=head_id, tid=tail_id,
    )
    assert len(edges) == 0

    # Kiểm tra file rejects được ghi nhận
    rejects_file = tmp_path / "loader_rejects.jsonl"
    assert rejects_file.exists()
    reject_content = rejects_file.read_text(encoding="utf-8")
    assert "FAKE_RELATION_XYZ" in reject_content


def test_merge_idempotent_no_duplicates(neo4j_ctx, tmp_path):
    """Yêu cầu 7: Chạy load hai lần trên cùng input cho số node và quan hệ bằng nhau."""
    store = neo4j_ctx.store
    e1_id = neo4j_ctx.make_id("ent_idem_1")
    e2_id = neo4j_ctx.make_id("ent_idem_2")

    entities = [
        {"id": e1_id, "name": "Nguyễn Trãi", "type": "Person", "start_year": 1380, "end_year": 1442},
        {"id": e2_id, "name": "Bình Ngô Đại Cáo", "type": "Work", "start_year": 1428},
    ]
    relations = [{
        "id": f"rel:{e1_id}:AUTHORED:{e2_id}",
        "head_id": e1_id,
        "tail_id": e2_id,
        "relation": "AUTHORED",
        "confidence": 1.0,
        "evidence_chunk_ids": ["c1"],
    }]
    (tmp_path / "entities.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entities), encoding="utf-8"
    )
    (tmp_path / "relations.jsonl").write_text(
        "\n".join(json.dumps(r) for r in relations), encoding="utf-8"
    )

    # Lần nạp 1
    load_resolved(store, str(tmp_path))
    compute_degree_and_display_names(store)

    cnt_nodes_1 = store.run(
        "MATCH (n) WHERE n.id IN [$e1, $e2] RETURN count(n) AS cnt",
        e1=e1_id, e2=e2_id,
    )[0]["cnt"]
    cnt_rels_1 = store.run(
        "MATCH (a:Entity {id: $e1})-[r]->(b:Entity {id: $e2}) RETURN count(r) AS cnt",
        e1=e1_id, e2=e2_id,
    )[0]["cnt"]

    # Lần nạp 2 trên cùng input
    load_resolved(store, str(tmp_path))
    compute_degree_and_display_names(store)

    cnt_nodes_2 = store.run(
        "MATCH (n) WHERE n.id IN [$e1, $e2] RETURN count(n) AS cnt",
        e1=e1_id, e2=e2_id,
    )[0]["cnt"]
    cnt_rels_2 = store.run(
        "MATCH (a:Entity {id: $e1})-[r]->(b:Entity {id: $e2}) RETURN count(r) AS cnt",
        e1=e1_id, e2=e2_id,
    )[0]["cnt"]

    assert cnt_nodes_1 == cnt_nodes_2 == 2
    assert cnt_rels_1 == cnt_rels_2 == 1


def test_resolver_to_loader_mentions_integration(neo4j_ctx, tmp_path):
    """Giai đoạn 6c: Test tích hợp resolver.run() -> loader.py trên Neo4j thật.

    1. Chạy resolver.run() trên fixture nhỏ (2 chunk, 2 entity).
    2. Xác nhận mentions.jsonl sinh ra đúng định dạng.
    3. Nạp vào Neo4j qua load_resolved và load_articles_chunks.
    4. Xác nhận quan hệ (:Chunk)-[:MENTIONS]->(:Entity) được tạo đúng trên Neo4j thật,
       số cạnh MENTIONS khớp chính xác số dòng trong mentions.jsonl.
    """
    store = neo4j_ctx.store
    p1_id = int(uuid.uuid4().int % 1000000)
    p2_id = p1_id + 1
    c1_id = neo4j_ctx.make_id("c1")
    c2_id = neo4j_ctx.make_id("c2")
    neo4j_ctx.track(p1_id, p2_id)

    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    ext_dir = tmp_path / "extracted"
    ext_dir.mkdir(parents=True, exist_ok=True)
    res_dir = tmp_path / "resolved"
    res_dir.mkdir(parents=True, exist_ok=True)

    # 1. Dữ liệu processed (articles & chunks)
    articles = [
        {"page_id": p1_id, "title": "Khởi nghĩa Lam Sơn"},
        {"page_id": p2_id, "title": "Phong trào Tây Sơn"},
    ]
    (proc_dir / "articles.jsonl").write_text(
        "\n".join(json.dumps(a) for a in articles), encoding="utf-8"
    )

    chunks = [
        {"id": c1_id, "page_id": p1_id, "page_title": "Khởi nghĩa Lam Sơn", "period_id": "le", "text": "Lê Lợi dựng cờ khởi nghĩa ở Lam Sơn."},
        {"id": c2_id, "page_id": p2_id, "page_title": "Phong trào Tây Sơn", "period_id": "tay-son", "text": "Nguyễn Huệ đại phá quân Thanh."},
    ]
    (proc_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(c) for c in chunks), encoding="utf-8"
    )

    # 2. Dữ liệu extracted (extractions)
    extractions = [
        {
            "chunk_id": c1_id,
            "entities": [{"name": f"Lê Lợi {neo4j_ctx.run_id}", "type": "Person"}],
            "triplets": [],
        },
        {
            "chunk_id": c2_id,
            "entities": [{"name": f"Nguyễn Huệ {neo4j_ctx.run_id}", "type": "Person"}],
            "triplets": [],
        },
    ]
    (ext_dir / "extractions.jsonl").write_text(
        "\n".join(json.dumps(e) for e in extractions), encoding="utf-8"
    )

    # 3. Chạy resolver.run()
    run_resolver(extracted_dir=ext_dir, resolved_dir=res_dir, processed_dir=proc_dir)

    mentions_file = res_dir / "mentions.jsonl"
    assert mentions_file.exists()
    mentions_rows = [json.loads(line) for line in mentions_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(mentions_rows) == 2

    # Đọc entities đã sinh để track ID dọn dẹp DB
    entities_file = res_dir / "entities.jsonl"
    ent_rows = [json.loads(line) for line in entities_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for ent in ent_rows:
        neo4j_ctx.track(ent["id"])

    # 4. Nạp vào Neo4j thật qua loader.py
    load_resolved(store, str(res_dir))
    load_articles_chunks(store, str(tmp_path))

    # 5. Xác nhận cạnh MENTIONS trên Neo4j thật
    records = store.run(
        "MATCH (c:Chunk)-[r:MENTIONS]->(e:Entity) "
        "WHERE c.id IN [$c1, $c2] "
        "RETURN c.id AS cid, e.id AS eid",
        c1=c1_id, c2=c2_id,
    )
    assert len(records) == 2
    assert len(records) == len(mentions_rows)

    found_pairs = {(r["cid"], r["eid"]) for r in records}
    expected_pairs = {(m["chunk_id"], m["entity_id"]) for m in mentions_rows}
    assert found_pairs == expected_pairs