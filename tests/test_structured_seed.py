"""Test trích xuất quan hệ Tier S (không LLM) từ Infobox, Wikidata và Backbone."""
from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from hgr.extract.structured_seed import (
    from_infobox,
    from_wikidata,
    from_backbone,
    load_ontology,
    load_infobox_map,
    reset_unmapped_wikidata_counts,
    get_unmapped_wikidata_counts,
    WIKIDATA_REL_MAP,
)
from hgr.extract.validator import validate_triplet


@pytest.fixture(autouse=True)
def _reset_counts():
    reset_unmapped_wikidata_counts()


def test_infobox_commanded_and_capital_of():
    """Kiểm tra chiều quan hệ infobox theo subject/object trong infobox_map.yaml:

    - 'chỉ huy': subject=value, object=page -> (Tướng) COMMANDED (Trận đánh)
    - 'thủ đô': subject=value, object=page -> (Kinh đô) CAPITAL_OF (Quốc gia)
    - 'tiền nhiệm' / 'kế nhiệm' / 'thân phụ': đúng chiều Person -> Person.
    """
    # 1. Trận đánh: chỉ huy
    battle_article = {
        "title": "Trận Bạch Đằng (938)",
        "page_id": 101,
        "start_year": 938,
        "end_year": 938,
        "infobox": {
            "template": "hộp thông tin xung đột quân sự",
            "fields": {
                "chỉ huy 1": {"text": "Ngô Quyền"},
                "địa điểm": {"text": "Sông Bạch Đằng"},
            },
        },
    }
    triplets = from_infobox(battle_article)
    assert len(triplets) == 2

    cmd_trip = next((t for t in triplets if t["relation"] == "COMMANDED"), None)
    assert cmd_trip is not None
    assert cmd_trip["head"] == "Ngô Quyền"
    assert cmd_trip["relation"] == "COMMANDED"
    assert cmd_trip["tail"] == "Trận Bạch Đằng (938)"
    assert cmd_trip["source"] == "infobox"
    assert cmd_trip["article_id"] == 101
    assert cmd_trip["confidence"] == 0.95

    loc_trip = next((t for t in triplets if t["relation"] == "OCCURRED_AT"), None)
    assert loc_trip is not None
    assert loc_trip["head"] == "Trận Bạch Đằng (938)"
    assert loc_trip["tail"] == "Sông Bạch Đằng"

    # 2. Quốc gia: thủ đô
    polity_article = {
        "title": "Nhà Lý",
        "page_id": 202,
        "infobox": {
            "template": "thông tin quốc gia cũ",
            "fields": {
                "thủ đô": {"text": "Thăng Long"},
            },
        },
    }
    polity_triplets = from_infobox(polity_article)
    assert len(polity_triplets) == 1
    cap_trip = polity_triplets[0]
    assert cap_trip["head"] == "Thăng Long"
    assert cap_trip["relation"] == "CAPITAL_OF"
    assert cap_trip["tail"] == "Nhà Lý"
    assert cap_trip["source"] == "infobox"
    assert cap_trip["article_id"] == 202

    # 3. Nhân vật hoàng gia: kế nhiệm, thân phụ, phối ngẫu
    royal_article = {
        "title": "Lý Thái Tông",
        "page_id": 303,
        "infobox": {
            "template": "thông tin nhân vật hoàng gia",
            "fields": {
                "thân phụ": {"text": "Lý Thái Tổ"},
                "phối ngẫu": {"text": "Kim Thiên Hoàng hậu"},
                "kế nhiệm": {"text": "Lý Thánh Tông"},
            },
        },
    }
    royal_triplets = from_infobox(royal_article)
    assert len(royal_triplets) == 3

    # Kế nhiệm: subject=value, object=page -> (Lý Thánh Tông) SUCCEEDED (Lý Thái Tông)
    succ_trip = next((t for t in royal_triplets if t["relation"] == "SUCCEEDED"), None)
    assert succ_trip is not None
    assert succ_trip["head"] == "Lý Thánh Tông"
    assert succ_trip["tail"] == "Lý Thái Tông"

    # Thân phụ: subject=page, object=value -> (Lý Thái Tông) CHILD_OF (Lý Thái Tổ)
    child_trip = next((t for t in royal_triplets if t["relation"] == "CHILD_OF"), None)
    assert child_trip is not None
    assert child_trip["head"] == "Lý Thái Tông"
    assert child_trip["tail"] == "Lý Thái Tổ"

    # Phối ngẫu: (Lý Thái Tông) SPOUSE_OF (Kim Thiên Hoàng hậu)
    spouse_trip = next((t for t in royal_triplets if t["relation"] == "SPOUSE_OF"), None)
    assert spouse_trip is not None
    assert spouse_trip["head"] == "Lý Thái Tông"
    assert spouse_trip["tail"] == "Kim Thiên Hoàng hậu"


def test_wikidata_relations_and_dropped_counting():
    """Kiểm tra quan hệ và chiều Wikidata cho P22, P26, P1365, P1366:

    - P22 (father): head = article, tail = target, CHILD_OF
    - P26 (spouse): head = article, tail = target, SPOUSE_OF
    - P1365 (replaces/thay thế cho): head = article (người kế nhiệm), tail = target, SUCCEEDED
    - P1366 (replaced by/được thay thế bởi): head = target (người kế nhiệm), tail = article, SUCCEEDED
    - Thuộc tính lạ không có trong ontology: bị bỏ qua và đếm, không sinh RELATED_TO.
    """
    article = {
        "title": "Lý Thái Tông",
        "page_id": 404,
        "start_year": 1000,
        "end_year": 1054,
        "wikidata": {
            "rels": {
                "P22": ["Q10788647"],
                "P26": ["Q10785123"],
                "P1365": ["Q10788647"],
                "P1366": ["Q10788655"],
                "P9999": ["Q999"],
                "P8888": ["Q888", "Q889"],
            },
            "rel_labels": {
                "Q10788647": {"label": "Lý Thái Tổ"},
                "Q10785123": {"label": "Kim Thiên Hoàng hậu"},
                "Q10788655": {"label": "Lý Thánh Tông"},
                "Q999": {"label": "Thực thể lạ 1"},
                "Q888": {"label": "Thực thể lạ 2"},
                "Q889": {"label": "Thực thể lạ 3"},
            },
        },
    }

    local_stats: dict[str, int] = {}
    triplets, dropped = from_wikidata(article, stats=local_stats, return_dropped=True)

    # 4 quan hệ hợp lệ
    assert len(triplets) == 4
    for t in triplets:
        assert t["relation"] != "RELATED_TO"
        assert t["source"] == "wikidata"
        assert t["article_id"] == 404

    # 1. P22: Lý Thái Tông CHILD_OF Lý Thái Tổ
    p22_trip = next((t for t in triplets if t["evidence"] == "wikidata:P22"), None)
    assert p22_trip is not None
    assert p22_trip["head"] == "Lý Thái Tông"
    assert p22_trip["relation"] == "CHILD_OF"
    assert p22_trip["tail"] == "Lý Thái Tổ"

    # 2. P26: Lý Thái Tông SPOUSE_OF Kim Thiên Hoàng hậu
    p26_trip = next((t for t in triplets if t["evidence"] == "wikidata:P26"), None)
    assert p26_trip is not None
    assert p26_trip["head"] == "Lý Thái Tông"
    assert p26_trip["relation"] == "SPOUSE_OF"
    assert p26_trip["tail"] == "Kim Thiên Hoàng hậu"

    # 3. P1365 (replaces/kế vị): Lý Thái Tông SUCCEEDED Lý Thái Tổ
    p1365_trip = next((t for t in triplets if t["evidence"] == "wikidata:P1365"), None)
    assert p1365_trip is not None
    assert p1365_trip["head"] == "Lý Thái Tông"
    assert p1365_trip["relation"] == "SUCCEEDED"
    assert p1365_trip["tail"] == "Lý Thái Tổ"

    # 4. P1366 (replaced by/được kế vị bởi): Lý Thánh Tông SUCCEEDED Lý Thái Tông
    p1366_trip = next((t for t in triplets if t["evidence"] == "wikidata:P1366"), None)
    assert p1366_trip is not None
    assert p1366_trip["head"] == "Lý Thánh Tông"
    assert p1366_trip["relation"] == "SUCCEEDED"
    assert p1366_trip["tail"] == "Lý Thái Tông"

    # Kiểm tra đếm thuộc tính lạ bị bỏ
    assert dropped.get("P9999") == 1
    assert dropped.get("P8888") == 2
    assert local_stats.get("P9999") == 1
    assert local_stats.get("P8888") == 2

    global_counts = get_unmapped_wikidata_counts()
    assert global_counts.get("P9999") == 1
    assert global_counts.get("P8888") == 2


def test_wikidata_additional_semantic_mappings():
    """Kiểm tra các thuộc tính bổ sung như P710 (PARTICIPATED_IN), P112 (FOUNDED), P36 (CAPITAL_OF)."""
    battle_article = {
        "title": "Chiến dịch Điện Biên Phủ",
        "wikidata": {
            "rels": {
                "P710": ["Q10800000"],
            },
            "rel_labels": {
                "Q10800000": {"label": "Võ Nguyên Giáp"},
            },
        },
    }
    triplets = from_wikidata(battle_article)
    assert len(triplets) == 1
    # P710: (Võ Nguyên Giáp) PARTICIPATED_IN (Chiến dịch Điện Biên Phủ)
    assert triplets[0]["head"] == "Võ Nguyên Giáp"
    assert triplets[0]["relation"] == "PARTICIPATED_IN"
    assert triplets[0]["tail"] == "Chiến dịch Điện Biên Phủ"

    polity_article = {
        "title": "Nhà Lý",
        "wikidata": {
            "rels": {
                "P112": ["Q10788647"],
                "P36": ["Q10788999"],
            },
            "rel_labels": {
                "Q10788647": {"label": "Lý Thái Tổ"},
                "Q10788999": {"label": "Thăng Long"},
            },
        },
    }
    polity_triplets = from_wikidata(polity_article)
    assert len(polity_triplets) == 2

    # P112: (Lý Thái Tổ) FOUNDED (Nhà Lý)
    founded = next(t for t in polity_triplets if t["relation"] == "FOUNDED")
    assert founded["head"] == "Lý Thái Tổ"
    assert founded["tail"] == "Nhà Lý"

    # P36: (Thăng Long) CAPITAL_OF (Nhà Lý)
    capital = next(t for t in polity_triplets if t["relation"] == "CAPITAL_OF")
    assert capital["head"] == "Thăng Long"
    assert capital["tail"] == "Nhà Lý"


def test_backbone_mocked_dynasty_and_country_name(tmp_path: Path):
    """Backbone giả lập một triều đại và một quốc hiệu: quan hệ thuộc ontology."""
    # Tạo fixture YAML cho backbone
    dynasty_file = tmp_path / "trieu_dai.yaml"
    dynasty_data = {
        "trieu_dai": [
            {"name": "Nhà Lý", "founder": "Lý Thái Tổ", "start": 1009, "end": 1225},
            {"name": "Nhà Trần", "predecessor": "Nhà Lý", "start": 1225, "end": 1400},
        ]
    }
    dynasty_file.write_text(yaml.dump(dynasty_data, allow_unicode=True), encoding="utf-8")

    country_file = tmp_path / "quoc_hieu.yaml"
    country_data = {
        "quoc_hieu": [
            {"name": "Văn Lang", "capital": "Phong Châu", "start": -2879, "end": -258},
            {"name": "Âu Lạc", "predecessor": "Văn Lang", "start": -257, "end": -179},
        ]
    }
    country_file.write_text(yaml.dump(country_data, allow_unicode=True), encoding="utf-8")

    capital_file = tmp_path / "kinh_do.yaml"
    capital_data = {
        "kinh_do": [
            {"place": "Thăng Long", "polity": "Nhà Lý", "start": 1010},
        ]
    }
    capital_file.write_text(yaml.dump(capital_data, allow_unicode=True), encoding="utf-8")

    ontology = load_ontology()
    valid_relations = set(ontology["relations"].keys())

    triplets = from_backbone(str(tmp_path))
    assert len(triplets) > 0

    for t in triplets:
        # Quan hệ bắt buộc thuộc ontology
        assert t["relation"] in valid_relations
        # Tuyệt đối không dùng RELATED_TO
        assert t["relation"] != "RELATED_TO"
        assert t["source"] == "backbone"
        assert t["confidence"] == 1.0

    # Kiểm tra các quan hệ cụ thể sinh ra
    relations_found = {t["relation"] for t in triplets}
    assert "FOUNDED" in relations_found
    assert "SUCCEEDED" in relations_found
    assert "CAPITAL_OF" in relations_found


def test_all_generated_triplets_pass_validator():
    """Mọi triplet sinh ra qua validator (ở phần kiểm tra kiểu) đều hợp lệ."""
    # Tập hợp các triplet sinh ra từ infobox, wikidata và backbone
    battle_article = {
        "title": "Trận Bạch Đằng (938)",
        "start_year": 938,
        "end_year": 938,
        "infobox": {
            "template": "hộp thông tin xung đột quân sự",
            "fields": {
                "chỉ huy 1": {"text": "Ngô Quyền"},
                "địa điểm": {"text": "Sông Bạch Đằng"},
            },
        },
    }
    infobox_triplets = from_infobox(battle_article)

    person_article = {
        "title": "Lý Thái Tông",
        "start_year": 1000,
        "end_year": 1054,
        "wikidata": {
            "rels": {
                "P22": ["Q1"],
                "P26": ["Q2"],
                "P1365": ["Q1"],
                "P1366": ["Q3"],
            },
            "rel_labels": {
                "Q1": {"label": "Lý Thái Tổ"},
                "Q2": {"label": "Kim Thiên Hoàng hậu"},
                "Q3": {"label": "Lý Thánh Tông"},
            },
        },
    }
    wikidata_triplets = from_wikidata(person_article)

    # Backbone thực tế từ configs/backbone
    real_backbone_triplets = from_backbone("configs/backbone")

    all_triplets = infobox_triplets + wikidata_triplets + real_backbone_triplets

    # Bảng phân loại thực thể để validator kiểm tra domain -> range
    entities = {
        # Nhân vật
        "Ngô Quyền": "Person",
        "Lý Thái Tổ": "Person",
        "Lý Thái Tông": "Person",
        "Lý Thánh Tông": "Person",
        "Kim Thiên Hoàng hậu": "Person",
        "Lý Thường Kiệt": "Person",
        "Trần Hưng Đạo": "Person",
        # Sự kiện
        "Trận Bạch Đằng (938)": "Event",
        # Địa danh
        "Sông Bạch Đằng": "Place",
        "Thăng Long": "Place",
        "Phong Châu": "Place",
        "Cổ Loa": "Place",
        "Hoa Lư": "Place",
        "Tây Đô": "Place",
        "Phú Xuân": "Place",
        "Huế": "Place",
        "Mê Linh": "Place",
        "Đồ Bàn": "Place",
        "Hoàng Đế thành": "Place",
        # Triều đại / Quốc gia
        "Văn Lang": "Polity",
        "Âu Lạc": "Polity",
        "Vạn Xuân": "Polity",
        "Đại Cồ Việt": "Polity",
        "Đại Việt": "Polity",
        "Đại Ngu": "Polity",
        "Việt Nam": "Polity",
        "Đại Nam": "Polity",
        "Đế quốc Việt Nam": "Polity",
        "Việt Nam Dân chủ Cộng hòa": "Polity",
        "Hồng Bàng": "Polity",
        "Nhà Thục": "Polity",
        "Nhà Tiền Lý": "Polity",
        "Nhà Ngô": "Polity",
        "Nhà Đinh": "Polity",
        "Nhà Tiền Lê": "Polity",
        "Nhà Lý": "Polity",
        "Nhà Trần": "Polity",
        "Nhà Hồ": "Polity",
        "Nhà Hậu Trần": "Polity",
        "Nhà Lê sơ": "Polity",
        "Nhà Mạc": "Polity",
        "Nhà Lê trung hưng": "Polity",
        "Nhà Tây Sơn": "Polity",
        "Nhà Nguyễn": "Polity",
        "Trưng Vương": "Polity",
        "Chăm Pa": "Polity",
    }

    ontology = load_ontology()

    for trip in all_triplets:
        # Không có triplet nào mang quan hệ RELATED_TO
        assert trip["relation"] != "RELATED_TO"
        res = validate_triplet(trip, entities=entities, ontology=ontology, max_year=1945)
        # Kiểm tra không vi phạm về kiểu thực thể hoặc quan hệ ontology
        bad_reasons = [r for r in res["reasons"] if r in ("relation_not_in_ontology", "head_type_invalid", "tail_type_invalid")]
        assert not bad_reasons, f"Triplet {trip} vi phạm kiểu hoặc quan hệ: {bad_reasons}"


def test_infobox_skips_field_label_placeholders_and_strips_parentheses():
    """Ô giá trị infobox đôi khi là nhãn trường ("Sáng lập triều đại") hoặc tên triều đại trong ngoặc."""
    article = {
        "title": "An Dương Vương",
        "page_id": 7,
        "start_year": 300,
        "end_year": 207,
        "infobox": {
            "template": "thông tin nhân vật hoàng gia",
            "fields": {
                "tiền nhiệm 1": {"text": "Sáng lập triều đại"},
                "kế nhiệm 1": {"text": "(Nhà Triệu)"},
            },
        },
    }
    tails = {t["tail"] if t["head"] == "An Dương Vương" else t["head"] for t in from_infobox(article)}
    assert "Sáng lập triều đại" not in tails
    assert "Nhà Triệu" in tails
    assert "(Nhà Triệu)" not in tails
