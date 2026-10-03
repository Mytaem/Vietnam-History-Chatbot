"""Test resolve/resolver.py: ID generation, 3-source alias loading, conditional fuzzy matching."""
from pathlib import Path
import json

from hgr.resolve.resolver import EntityResolver, _slug


def test_resolver_uses_curated_historical_place_aliases():
    resolver = EntityResolver()
    resolver.add_aliases("local:ha_noi", ["Hà Nội", "Thăng Long", "Đông Kinh"])

    assert resolver.resolve({"name": "thăng long"}, [], "ly") == "local:ha_noi"
    assert _slug("Đại Việt") == "dai-viet"


def test_resolver_keeps_same_named_events_in_different_years_separate():
    resolver = EntityResolver()

    battle_938 = resolver.resolve({"name": "Trận Bạch Đằng 938"}, [], "ngo")
    battle_981 = resolver.resolve({"name": "Trận Bạch Đằng 981"}, [], "tienle")
    battle_1288 = resolver.resolve({"name": "Trận Bạch Đằng 1288"}, [], "tran")

    assert len({battle_938, battle_981, battle_1288}) == 3


def test_resolver_prefers_wikidata_id():
    resolver = EntityResolver()

    assert resolver.resolve({"name": "Hồ Chí Minh", "qid": "Q7186"}, [], "candai") == "qid:Q7186"


def test_three_bach_dang_battles_separate_ids_by_year():
    """Ba 'Trận Bạch Đằng' (938, 981, 1288) cùng type Event, tên giống nhau: sinh 3 ID khác nhau theo năm."""
    resolver = EntityResolver()

    b1 = resolver.resolve({"name": "Trận Bạch Đằng", "type": "Event", "start_year": 938})
    b2 = resolver.resolve({"name": "Trận Bạch Đằng", "type": "Event", "start_year": 981})
    b3 = resolver.resolve({"name": "Trận Bạch Đằng", "type": "Event", "start_year": 1288})

    assert b1 == "local:tran-bach-dang-938"
    assert b2 == "local:tran-bach-dang-981"
    assert b3 == "local:tran-bach-dang-1288"
    assert len({b1, b2, b3}) == 3


def test_tran_hung_dao_and_hung_dao_dai_vuong_merged():
    """Trần Hưng Đạo và Hưng Đạo Đại Vương được gộp về cùng 1 ID chuẩn qua alias và thuộc tính."""
    # Cách 1: Nạp alias trước (từ Wikidata hoặc backbone)
    resolver = EntityResolver()
    resolver.add_aliases(
        "local:tran-hung-dao",
        ["Trần Hưng Đạo", "Hưng Đạo Đại Vương", "Trần Quốc Tuấn"],
        ent_type="Person",
    )
    assert resolver.resolve({"name": "Trần Hưng Đạo", "type": "Person"}) == "local:tran-hung-dao"
    assert resolver.resolve({"name": "Hưng Đạo Đại Vương", "type": "Person"}) == "local:tran-hung-dao"

    # Cách 2: Thực thể đầu tiên mang theo danh sách aliases khi LLM trích xuất
    r2 = EntityResolver()
    id1 = r2.resolve({"name": "Trần Hưng Đạo", "type": "Person", "aliases": ["Hưng Đạo Đại Vương"]})
    id2 = r2.resolve({"name": "Hưng Đạo Đại Vương", "type": "Person"})
    assert id1 == id2 == "local:tran-hung-dao"


def test_same_name_different_types_not_merged():
    """Hai thực thể cùng tên nhưng khác type (ví dụ Person 'Hoa Lư' và Place 'Hoa Lư'): KHÔNG bị gộp."""
    resolver = EntityResolver()

    p_id = resolver.resolve({"name": "Hoa Lư", "type": "Person"})
    pl_id = resolver.resolve({"name": "Hoa Lư", "type": "Place"})

    assert p_id != pl_id
    assert p_id == "local:hoa-lu"
    assert pl_id == "local:hoa-lu-place"


def test_events_similar_name_different_years_outside_tolerance_not_merged():
    """Hai Event trùng tên gần đúng nhưng năm cách nhau xa (ngoài tolerance): KHÔNG bị gộp."""
    resolver = EntityResolver(event_year_tolerance=1)

    e1 = resolver.resolve({"name": "Chiến dịch Bạch Đằng", "type": "Event", "start_year": 938})
    e2 = resolver.resolve({"name": "Trận chiến Bạch Đằng", "type": "Event", "start_year": 1288})

    assert e1 != e2
    assert e1 == "local:chien-dich-bach-dang-938"
    assert e2 == "local:tran-chien-bach-dang-1288"


def test_events_similar_name_within_tolerance_are_merged():
    """Hai Event tên gần giống nhau (token_set_ratio >= 92) và năm chênh lệch <= tolerance: ĐƯỢC gộp."""
    resolver = EntityResolver(event_year_tolerance=1)

    e1 = resolver.resolve({"name": "Khởi nghĩa Lam Sơn", "type": "Event", "start_year": 1418})
    e2 = resolver.resolve({"name": "Cuộc khởi nghĩa Lam Sơn", "type": "Event", "start_year": 1418})

    assert e1 == e2 == "local:khoi-nghia-lam-son-1418"


def test_wikidata_qid_always_preferred_and_not_confused():
    """Entity có QID Wikidata luôn trả về qid:Q... bất kể tên trùng với entity khác."""
    resolver = EntityResolver()

    q1 = resolver.resolve({"name": "Bạch Đằng", "qid": "Q12345"})
    q2 = resolver.resolve({"name": "Bạch Đằng", "qid": "qid:Q98765"})

    assert q1 == "qid:Q12345"
    assert q2 == "qid:Q98765"
    assert q1 != q2


def test_aliases_from_three_sources_lead_to_correct_id(tmp_path):
    """Alias từ 3 nguồn (dia_danh.yaml, Wikidata articles, backbone) đều dẫn đúng về ID chuẩn."""
    resolver = EntityResolver()

    # Nguồn 1: dia_danh.yaml (Place)
    dia_danh_file = tmp_path / "dia_danh.yaml"
    dia_danh_file.write_text(
        "dia_danh:\n"
        "  - id: ha_noi\n"
        "    canonical: Hà Nội\n"
        "    names:\n"
        "      - {name: Thăng Long}\n"
        "      - {name: Đông Đô}\n",
        encoding="utf-8",
    )
    resolver.load_dia_danh(dia_danh_file)
    assert resolver.resolve({"name": "Đông Đô", "type": "Place"}) == "local:ha_noi"

    # Nguồn 2: backbone (trieu_dai.yaml & quoc_hieu.yaml)
    backbone_dir = tmp_path / "backbone"
    backbone_dir.mkdir(parents=True, exist_ok=True)
    (backbone_dir / "trieu_dai.yaml").write_text(
        "trieu_dai:\n"
        "  - {name: Nhà Hậu Trần, start: 1407, end: 1414, aliases: [Hậu Trần]}\n",
        encoding="utf-8",
    )
    (backbone_dir / "quoc_hieu.yaml").write_text(
        "quoc_hieu:\n"
        "  - {name: Đại Cồ Việt, start: 968, end: 1054}\n",
        encoding="utf-8",
    )
    resolver.load_backbone(backbone_dir)
    assert resolver.resolve({"name": "Hậu Trần", "type": "Polity"}) == "local:nha-hau-tran"
    assert resolver.resolve({"name": "Đại Cồ Việt", "type": "Polity"}) == "local:dai-co-viet"

    # Nguồn 3: Wikidata articles (articles.jsonl)
    articles_data = [
        {
            "title": "Hồ Chí Minh",
            "qid": "Q7186",
            "label": "Hồ Chí Minh",
            "aliases": ["Nguyễn Ái Quốc", "Bác Hồ", "Nguyễn Sinh Cung"],
            "redirects": ["Nguyễn Tất Thành"],
            "type": "Person",
        }
    ]
    resolver.load_articles(articles_data)
    assert resolver.resolve({"name": "Nguyễn Ái Quốc", "type": "Person"}) == "qid:Q7186"
    assert resolver.resolve({"name": "Bác Hồ", "type": "Person"}) == "qid:Q7186"
    assert resolver.resolve({"name": "Nguyễn Tất Thành", "type": "Person"}) == "qid:Q7186"


def test_event_without_year_not_fuzzy_merged_with_event_with_year():
    """Entity thiếu năm mà type là Event: không bị fuzzy-gộp với entity có năm (an toàn, tách riêng)."""
    resolver = EntityResolver()

    e_year = resolver.resolve({"name": "Trận Chi Lăng", "type": "Event", "start_year": 1427})
    e_noyear = resolver.resolve({"name": "Trận Chi Lăng", "type": "Event", "start_year": None})

    assert e_year != e_noyear
    assert e_year == "local:tran-chi-lang-1427"
    assert e_noyear == "local:tran-chi-lang"


def test_parameter_tuning_changes_resolution_behavior():
    """Đổi fuzzy_threshold hoặc event_year_tolerance qua tham số: hành vi gộp/tách thay đổi tương ứng."""
    # 1. event_year_tolerance:
    # 1788 và 1789 (chênh lệch 1 năm)
    r_tol0 = EntityResolver(event_year_tolerance=0)
    e1_t0 = r_tol0.resolve({"name": "Trận Ngọc Hồi Đống Đa", "type": "Event", "start_year": 1788})
    e2_t0 = r_tol0.resolve({"name": "Trận Ngọc Hồi - Đống Đa", "type": "Event", "start_year": 1789})
    assert e1_t0 != e2_t0

    r_tol1 = EntityResolver(event_year_tolerance=1)
    e1_t1 = r_tol1.resolve({"name": "Trận Ngọc Hồi Đống Đa", "type": "Event", "start_year": 1788})
    e2_t1 = r_tol1.resolve({"name": "Trận Ngọc Hồi - Đống Đa", "type": "Event", "start_year": 1789})
    assert e1_t1 == e2_t1 == "local:tran-ngoc-hoi-dong-da-1788"

    # 2. fuzzy_threshold:
    # "Lý Thường Kiệt" vs "Lý Thường"
    r_strict = EntityResolver(fuzzy_threshold=95)
    p1 = r_strict.resolve({"name": "Lý Thường Kiệt", "type": "Person"})
    p2 = r_strict.resolve({"name": "Lý Thường", "type": "Person"})
    assert p1 != p2

    r_loose = EntityResolver(fuzzy_threshold=70)
    p3 = r_loose.resolve({"name": "Lý Thường Kiệt", "type": "Person"})
    p4 = r_loose.resolve({"name": "Lý Thường", "type": "Person"})
    assert p3 == p4


def test_mismatched_wikilink_in_chunk_links_is_rejected_and_falls_through():
    """Một wikilink trong chunk_links trỏ đến ID/tên KHÔNG khớp với tên thực thể: bị từ chối và rơi xuống bước tiếp theo."""
    resolver = EntityResolver()

    # Thực thể cần resolve là "Lê Lợi"
    # chunk_links chứa link của một thực thể khác không liên quan
    mismatched_links = [
        {"surface": "Lam Sơn", "target": "Khởi nghĩa Lam Sơn", "qid": "Q10780287"},
        {"surface": "Đông Đô", "target": "Hà Nội", "qid": "Q1858"},
    ]

    resolved_id = resolver.resolve(
        {"name": "Lê Lợi", "type": "Person"},
        chunk_links=mismatched_links,
    )

    # Hệ thống từ chối các link không khớp tên, không bị gán nhầm sang QID của link sai
    assert resolved_id != "qid:Q10780287"
    assert resolved_id != "qid:Q1858"
    # Rơi xuống bước sinh local ID theo đúng thực thể
    assert resolved_id == "local:le-loi"


def test_real_rapidfuzz_metrics():
    """Xác minh và in số liệu thật 100% của rapidfuzz cho các cặp thực thể lịch sử."""
    from rapidfuzz import fuzz

    pairs = [
        ("Lý Thường", "Lý Thường Kiệt"),
        ("Trần Hưng Đạo", "Hưng Đạo Đại Vương"),
        ("Trận Bạch Đằng", "Bạch Đằng"),
        ("Trận Bạch Đằng", "Chiến dịch Bạch Đằng"),
        ("Trận Bạch Đằng", "Trận đánh Bạch Đằng"),
        ("Trận Bạch Đằng", "Chiến thắng Bạch Đằng"),
    ]

    results = {}
    for s1, s2 in pairs:
        c1, c2 = s1.lower(), s2.lower()
        t_set = fuzz.token_set_ratio(c1, c2)
        t_sort = fuzz.token_sort_ratio(c1, c2)
        avg = (t_set + t_sort) / 2.0
        m = min(t_set, t_sort)
        results[(s1, s2)] = (t_set, t_sort, avg, m)

    # Kiểm tra số thật chính xác
    # a. "Lý Thường" vs "Lý Thường Kiệt"
    set_a, sort_a, avg_a, min_a = results[("Lý Thường", "Lý Thường Kiệt")]
    assert set_a == 100.0
    assert round(sort_a, 2) == 78.26
    assert round(avg_a, 2) == 89.13
    assert round(min_a, 2) == 78.26

    # b. "Trần Hưng Đạo" vs "Hưng Đạo Đại Vương"
    set_b, sort_b, avg_b, min_b = results[("Trần Hưng Đạo", "Hưng Đạo Đại Vương")]
    assert round(set_b, 2) == 76.19
    assert round(sort_b, 2) == 64.52
    assert round(avg_b, 2) == 70.35
    assert round(min_b, 2) == 64.52


def test_ly_thuong_and_ly_thuong_kiet_always_split_at_threshold_92():
    """Khẳng định: ở ngưỡng 92, cặp 'Lý Thường' / 'Lý Thường Kiệt' luôn TÁCH (không phụ thuộc config runtime).

    Nếu sau này ai vô tình đổi công thức (ví dụ chỉ dùng token_set_ratio) hoặc hạ threshold dưới ~90,
    test này sẽ báo đỏ ngay lập tức để bảo vệ tính toàn vẹn dữ liệu thực thể.
    """
    resolver = EntityResolver(fuzzy_threshold=92)
    id1 = resolver.resolve({"name": "Lý Thường", "type": "Person"}, [], "ly")
    id2 = resolver.resolve({"name": "Lý Thường Kiệt", "type": "Person"}, [], "ly")

    assert id1 != id2
    assert id1 == "local:ly-thuong"
    assert id2 == "local:ly-thuong-kiet"


def test_resolver_run_generates_mentions_jsonl(tmp_path):
    """Kiểm tra resolver.run() sinh mentions.jsonl đúng cấu trúc và khớp với entities.jsonl."""
    from hgr.resolve.resolver import run as run_resolver

    ext_dir = tmp_path / "extracted"
    ext_dir.mkdir(parents=True, exist_ok=True)
    res_dir = tmp_path / "resolved"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        {"id": "c1", "page_id": 1, "page_title": "Nhà Lê", "period_id": "le"},
        {"id": "c2", "page_id": 2, "page_title": "Nhà Nguyễn", "period_id": "nguyen"},
    ]
    (proc_dir / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")

    extractions = [
        {
            "chunk_id": "c1",
            "entities": [{"name": "Lê Lợi", "type": "Person"}],
            "triplets": [],
        },
        {
            "chunk_id": "c2",
            "entities": [{"name": "Nguyễn Ánh", "type": "Person"}],
            "triplets": [],
        },
    ]
    (ext_dir / "extractions.jsonl").write_text("\n".join(json.dumps(e) for e in extractions), encoding="utf-8")

    run_resolver(extracted_dir=ext_dir, resolved_dir=res_dir, processed_dir=proc_dir)

    mentions_file = res_dir / "mentions.jsonl"
    assert mentions_file.exists()
    lines = [json.loads(line) for line in mentions_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2

    # Mỗi dòng có chunk_id và entity_id
    assert lines[0]["chunk_id"] == "c1"
    assert lines[0]["entity_id"] == "local:le-loi"
    assert lines[1]["chunk_id"] == "c2"
    assert lines[1]["entity_id"] == "local:nguyen-anh"

    # Khớp với entities.jsonl
    entities_file = res_dir / "entities.jsonl"
    ent_ids = {json.loads(l)["id"] for l in entities_file.read_text(encoding="utf-8").splitlines() if l.strip()}
    for row in lines:
        assert row["entity_id"] in ent_ids


def test_resolver_run_mentions_idempotent_and_deduplicates(tmp_path):
    """Kiểm tra resolver.run() ghi đè idempotent (không nhân đôi) và lọc trùng lặp trong cùng chunk."""
    from hgr.resolve.resolver import run as run_resolver

    ext_dir = tmp_path / "extracted"
    ext_dir.mkdir(parents=True, exist_ok=True)
    res_dir = tmp_path / "resolved"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    chunks = [{"id": "c1", "page_id": 1, "page_title": "Nhà Lê", "period_id": "le"}]
    (proc_dir / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")

    # Cùng 1 entity được nhắc 3 lần trong cùng 1 chunk
    extractions = [{
        "chunk_id": "c1",
        "entities": [
            {"name": "Lê Lợi", "type": "Person"},
            {"name": "Lê Lợi", "type": "Person"},
            {"name": "Lê Lợi", "type": "Person"},
        ],
        "triplets": [],
    }]
    (ext_dir / "extractions.jsonl").write_text("\n".join(json.dumps(e) for e in extractions), encoding="utf-8")

    # Lần chạy 1
    run_resolver(extracted_dir=ext_dir, resolved_dir=res_dir, processed_dir=proc_dir)
    mentions_file = res_dir / "mentions.jsonl"
    lines_run1 = mentions_file.read_text(encoding="utf-8").splitlines()
    assert len(lines_run1) == 1  # Lọc trùng lặp thành công

    # Lần chạy 2 (idempotent, không nhân đôi)
    run_resolver(extracted_dir=ext_dir, resolved_dir=res_dir, processed_dir=proc_dir)
    lines_run2 = mentions_file.read_text(encoding="utf-8").splitlines()
    assert len(lines_run2) == 1
    assert lines_run1 == lines_run2






def test_structured_triplet_type_uses_ontology_domain_range_not_blanket_polity(tmp_path):
    """Trước đây mọi head/tail của Tier S bị gán cứng 'Polity' trừ CAPITAL_OF, mistype gần hết Person
    (CHILD_OF, SPOUSE_OF, RULED, PARTICIPATED_IN...) khi họ chưa được LLM trích xuất từ trước."""
    from hgr.resolve.resolver import run as run_resolver

    ext_dir = tmp_path / "extracted"
    ext_dir.mkdir(parents=True, exist_ok=True)
    res_dir = tmp_path / "resolved"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / "chunks.jsonl").write_text("", encoding="utf-8")

    structured = [
        {"head": "Trần Hưng Đạo", "relation": "CHILD_OF", "tail": "Trần Liễu", "source": "wikidata"},
        {"head": "Trần Hưng Đạo", "relation": "PARTICIPATED_IN", "tail": "Trận Bạch Đằng (1288)", "source": "wikidata"},
        {"head": "Cổ Loa", "relation": "CAPITAL_OF", "tail": "Âu Lạc", "source": "backbone"},
    ]
    (ext_dir / "structured.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in structured), encoding="utf-8"
    )

    run_resolver(extracted_dir=ext_dir, resolved_dir=res_dir, processed_dir=proc_dir)
    entities = {
        json.loads(l)["name"]: json.loads(l)["type"]
        for l in (res_dir / "entities.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()
    }
    assert entities["Trần Hưng Đạo"] == "Person"
    assert entities["Trần Liễu"] == "Person"
    assert entities["Trận Bạch Đằng (1288)"] == "Event"
    assert entities["Cổ Loa"] == "Place"
    assert entities["Âu Lạc"] == "Polity"


def test_structured_type_guess_never_overrides_known_backbone_type(tmp_path):
    """SUCCEEDED/PARTICIPATED_IN có domain đa loại ([Person, Polity, ...]); đoán domain[0]='Person' làm
    'Nhà Trần' (Polity theo backbone) bị tách thành 2 entity khác id khi nó cũng là head/tail của quan hệ
    đó. Backbone đã biết type phải luôn thắng type đoán từ domain/range."""
    from hgr.resolve.resolver import run as run_resolver

    ext_dir = tmp_path / "extracted"
    ext_dir.mkdir(parents=True, exist_ok=True)
    res_dir = tmp_path / "resolved"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / "chunks.jsonl").write_text("", encoding="utf-8")

    structured = [
        {"head": "Nhà Hồ", "relation": "SUCCEEDED", "tail": "Nhà Trần"},
        {"head": "Nhà Trần", "relation": "PARTICIPATED_IN", "tail": "Trận Bạch Đằng (1288)"},
    ]
    (ext_dir / "structured.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in structured), encoding="utf-8"
    )

    run_resolver(extracted_dir=ext_dir, resolved_dir=res_dir, processed_dir=proc_dir)
    entities = [json.loads(l) for l in (res_dir / "entities.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    tran = [e for e in entities if e["name"] == "Nhà Trần"]
    assert len(tran) == 1, f"'Nhà Trần' bị tách thành {len(tran)} entity: {tran}"
    assert tran[0]["type"] == "Polity"


def test_structured_year_only_applies_to_the_side_it_belongs_to(tmp_path):
    """start_year/end_year của triplet Tier S là năm của bài viết chủ thể; P710 (participant) có
    head_is_target=True nên head=bên tham chiến, tail=article(sự kiện) -> năm thuộc tail, không phải head.
    Gán nhầm cho cả hai bên làm sai năm sinh/mất của vợ/cha/người kế nhiệm khi head là Person."""
    from hgr.resolve.resolver import run as run_resolver

    ext_dir = tmp_path / "extracted"
    ext_dir.mkdir(parents=True, exist_ok=True)
    res_dir = tmp_path / "resolved"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / "chunks.jsonl").write_text("", encoding="utf-8")

    structured = [
        {"head": "Nhà Trần", "relation": "PARTICIPATED_IN", "tail": "Trận Bạch Đằng (1288)",
         "start_year": 1288, "end_year": 1288, "year_target": "tail"},
        {"head": "Quang Trung", "relation": "CHILD_OF", "tail": "Hồ Phi Phúc",
         "start_year": 1752, "end_year": 1792, "year_target": "head"},
    ]
    (ext_dir / "structured.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in structured), encoding="utf-8"
    )
    run_resolver(extracted_dir=ext_dir, resolved_dir=res_dir, processed_dir=proc_dir)
    entities = {
        json.loads(l)["name"]: json.loads(l)
        for l in (res_dir / "entities.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()
    }
    assert entities["Nhà Trần"]["start_year"] is None  # không phải năm trận đánh
    assert entities["Trận Bạch Đằng (1288)"]["start_year"] == 1288
    assert entities["Quang Trung"]["start_year"] == 1752
    assert entities["Hồ Phi Phúc"]["start_year"] is None  # không phải năm sinh/mất của Quang Trung


def test_llm_emitted_non_qid_is_not_used_as_wikidata_id():
    """LLM điền tên/năm vào trường qid (vd "Âu Lạc", "208 TCN"); những giá trị này không được thành ID qid:."""
    from hgr.resolve.resolver import _valid_qid

    assert _valid_qid("Âu Lạc") is None
    assert _valid_qid("208 TCN") is None
    assert _valid_qid("Q210417") == "Q210417"
    assert _valid_qid("qid:Q210417") == "Q210417"
    assert _valid_qid(None) is None
