"""Test cho schemas.py, prompts.py, few-shot theo era, validator kiểm định và ước lượng token."""
from __future__ import annotations

from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError

from hgr.extract.schemas import Entity, EntityOutput, Triplet, RelationOutput, EntityType, RelType
from hgr.extract.prompts import (
    PROMPT_VERSION,
    ENTITY_SYSTEM,
    RELATION_SYSTEM,
    FEW_SHOT_BY_ERA,
    build_entity_messages,
    build_relation_messages,
)
from hgr.extract.validator import validate_triplet, load_ontology

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = PROJECT_ROOT / "configs" / "ontology.yaml"
PERIODS_PATH = PROJECT_ROOT / "configs" / "periods.yaml"


def test_no_related_to_in_ontology_schema_prompts():
    """Quan hệ RELATED_TO đã được gỡ bỏ hoàn toàn khỏi ontology, schemas và prompts."""
    # 1. Trong ontology.yaml
    ontology_data = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    assert "RELATED_TO" not in ontology_data.get("relations", {})

    # 2. Trong schemas.py Enum
    rel_names = [e.value for e in RelType]
    assert "RELATED_TO" not in rel_names
    assert len(rel_names) == 21  # Đúng 21 quan hệ nghiệp vụ

    # 3. Trong prompts.py
    prompts_code = (PROJECT_ROOT / "src" / "hgr" / "extract" / "prompts.py").read_text(encoding="utf-8")
    assert "RELATED_TO" not in prompts_code


def test_schemas_enum_validation():
    """JSON schema sinh từ EntityOutput/RelationOutput có enum đúng theo ontology; giá trị ngoài enum bị từ chối."""
    # 1. Kiểm tra JSON Schema sinh ra
    entity_schema = EntityOutput.model_json_schema()
    rel_schema = RelationOutput.model_json_schema()

    # Kiểm tra enum của EntityType và RelType có trong $defs
    defs = entity_schema.get("$defs", {})
    assert "EntityType" in defs
    assert set(defs["EntityType"]["enum"]) == {"Person", "Event", "Place", "Polity", "Organization", "Work", "Culture"}

    rel_defs = rel_schema.get("$defs", {})
    assert "RelType" in rel_defs
    assert "COMMANDED" in rel_defs["RelType"]["enum"]
    assert "SUCCEEDED" in rel_defs["RelType"]["enum"]
    assert "RELATED_TO" not in rel_defs["RelType"]["enum"]

    # Kiểm tra tương thích ngược __args__ cho loader.py (allowed_types = set(RelType.__args__))
    assert hasattr(RelType, "__args__")
    assert "COMMANDED" in RelType.__args__
    assert "RELATED_TO" not in RelType.__args__
    assert hasattr(EntityType, "__args__")
    assert "Person" in EntityType.__args__

    # 2. Giá trị hợp lệ
    valid_entity = Entity(
        name="Lý Thường Kiệt",
        type="Person",
        description="Danh tướng thời Lý",
        start_year=1019,
        end_year=1105,
    )
    assert valid_entity.name == "Lý Thường Kiệt"

    valid_triplet = Triplet(
        head="Lý Thường Kiệt",
        relation="COMMANDED",
        tail="Trận Như Nguyệt",
        evidence="Lý Thường Kiệt chỉ huy quân dân đánh tan quân Tống",
    )
    assert valid_triplet.relation == RelType.COMMANDED

    # 3. Giá trị ngoài enum bị Pydantic ValidationError từ chối
    with pytest.raises(ValidationError):
        Entity(name="Thần đèn", type="Alien")  # Type không có trong ontology

    with pytest.raises(ValidationError):
        Triplet(
            head="A",
            relation="RELATED_TO",  # Đã bị gỡ, không còn trong RelType
            tail="B",
            evidence="A và B liên quan với nhau",
        )

    with pytest.raises(ValidationError):
        Triplet(
            head="A",
            relation="UNKNOWN_REL",
            tail="B",
            evidence="bằng chứng",
        )


def test_all_few_shots_pass_validator_and_have_exact_evidence():
    """Với mọi few-shot: evidence là chuỗi con nguyên văn của đoạn văn, và triplet qua validator hợp lệ 100%."""
    ontology = load_ontology()
    eras_tested = set()

    for era_id, examples in FEW_SHOT_BY_ERA.items():
        eras_tested.add(era_id)
        assert len(examples) >= 1, f"Era {era_id} thiếu few-shot example"
        for ex in examples:
            chunk = ex["chunk"]
            chunk_text = chunk["text"]
            entities = ex["entities"]
            triplets = ex["triplets"]

            # Map tên thực thể -> type để validator kiểm tra domain/range
            entity_map = {e["name"]: e["type"] for e in entities}

            # Kiểm tra từng thực thể
            for ent in entities:
                assert ent["type"] in ontology["entity_types"]

            # Kiểm tra từng triplet
            for trip in triplets:
                # 1. evidence phải là chuỗi con nguyên văn 100% của chunk_text
                evidence = trip["evidence"]
                assert evidence in chunk_text, (
                    f"Evidence '{evidence}' không có nguyên văn trong chunk text của era '{era_id}':\n{chunk_text}"
                )

                # 2. Kiểm tra quan hệ thuộc ontology
                assert trip["relation"] in ontology["relations"]
                assert trip["relation"] != "RELATED_TO"

                # 3. Chạy qua validator
                res = validate_triplet(
                    trip,
                    entities=entity_map,
                    chunk_text=chunk_text,
                    ontology=ontology,
                    max_year=1945,
                )
                assert res["ok"] is True, f"Few-shot triplet {trip} bị validator từ chối: {res['reasons']}"

    # Đảm bảo bao phủ đủ 5 era chính
    for required_era in ("tiensu", "dungnuoc", "bacthuoc", "phongkien", "candai"):
        assert required_era in eras_tested


def test_build_messages_with_periods():
    """Với mỗi era, build_entity_messages và build_relation_messages chạy được và chứa role_vocab/polities."""
    periods_data = yaml.safe_load(PERIODS_PATH.read_text(encoding="utf-8"))
    eras = periods_data.get("eras", [])
    assert len(eras) >= 5

    dummy_chunk = {
        "text": "Ngô Quyền đánh tan quân Nam Hán trên sông Bạch Đằng năm 938.",
        "page_title": "Ngô Quyền",
        "section_path": "Chiến sự",
        "header": "[Bài: Ngô Quyền | Mục: Chiến sự]",
        "links": ["Nam Hán", "sông Bạch Đằng"],
    }
    dummy_entities = [
        {"name": "Ngô Quyền", "type": "Person"},
        {"name": "Nam Hán", "type": "Polity"},
        {"name": "sông Bạch Đằng", "type": "Place"},
        {"name": "Trận Bạch Đằng (938)", "type": "Event"},
    ]

    for era in eras:
        era_id = era["id"]
        periods = era.get("periods", [])
        if not periods:
            continue
        period = periods[0]
        period["era_id"] = era_id

        # 1. build_entity_messages
        ent_msgs = build_entity_messages(dummy_chunk, period=period)
        assert len(ent_msgs) >= 2
        assert ent_msgs[0]["role"] == "system"
        assert ENTITY_SYSTEM in ent_msgs[0]["content"]

        last_user_msg = ent_msgs[-1]["content"]
        assert dummy_chunk["text"] in last_user_msg
        # Kiểm tra role_vocab hoặc polities nếu period có
        if period.get("role_vocab"):
            assert period["role_vocab"][0] in last_user_msg
        if period.get("polities"):
            assert period["polities"][0] in last_user_msg

        # 2. build_relation_messages
        rel_msgs = build_relation_messages(dummy_chunk, entities=dummy_entities, period=period)
        assert len(rel_msgs) >= 2
        assert rel_msgs[0]["role"] == "system"
        assert RELATION_SYSTEM in rel_msgs[0]["content"]

        last_rel_user = rel_msgs[-1]["content"]
        assert "Ngô Quyền (Person)" in last_rel_user
        assert "QUAN HỆ HỢP LỆ" in last_rel_user
        # Kiểm tra quan hệ rút gọn khả thi: có Person và Event nên có COMMANDED
        assert "COMMANDED" in last_rel_user
        # Không có Work hay Culture nên không liệt kê AUTHORED hay FOUND_AT
        assert "AUTHORED" not in last_rel_user
        assert "FOUND_AT" not in last_rel_user


def test_prompt_token_length_estimation():
    """Ước lượng độ dài: prompt Pass 1 và Pass 2 cộng một đoạn 500 token nằm gọn trong khoảng 3000 token.

    Phương pháp ước lượng:
    - Tiếng Việt chuẩn BPE (như tokenizer của Qwen/BGE): trung bình 1 từ tiếng Việt ~ 1.3 token,
      hoặc ước lượng thô theo ký tự: 1 token ~ 3.5 ký tự.
    - Công thức ước tính an toàn: estimated_tokens = max(len(text.split()) * 1.3, len(text) / 3.0)
    """
    # Tạo đoạn văn mẫu dài ~500 token (~380 từ tiếng Việt)
    sample_500_tokens_text = (
        "Tháng 4 năm 1288, quân và dân Đại Việt dưới sự chỉ huy tài ba của Hưng Đạo Đại vương Trần Quốc Tuấn "
        "đã tổ chức phục kích tiêu diệt toàn bộ đạo thủy binh xâm lược của đế quốc Nguyên Mông trên sông Bạch Đằng. "
        "Trước đó, Ô Mã Nhi và Phàn Tiếp dẫn đoàn thuyền chiến rút chạy ra biển theo đường sông Bạch Đằng. "
        "Trần Hưng Đạo đã cho cắm bãi cọc gỗ lim bịt sắt nhọn vát đầu dưới lòng sông ở những vị trí hiểm yếu gần cửa biển. "
        "Khi thủy triều dâng cao, quân ta đem thuyền nhẹ ra khiêu chiến rồi giả vờ thua chạy để nhử địch vượt qua bãi cọc. "
        "Đúng lúc thủy triều bắt đầu rút mạnh, thuyền chiến nặng nề của quân Nguyên bị mắc kẹt, va thủng và nghiêng đắm hàng loạt. "
        "Quân Đại Việt từ các nhánh sông đổ ra đánh tạt sườn, phóng hỏa tiễn thiêu rụi chiến thuyền giặc. "
        "Tướng Ô Mã Nhi bị bắt sống tại trận, kết thúc hoàn toàn cuộc kháng chiến chống quân Nguyên Mông lần thứ ba, "
        "bảo vệ vững chắc nền độc lập chủ quyền của Đại Việt và để lại bài học quân sự kinh điển cho hậu thế."
    )

    chunk = {
        "text": sample_500_tokens_text,
        "page_title": "Trận Bạch Đằng (1288)",
        "section_path": "Diễn biến chiến sự",
        "header": "[Bài: Trận Bạch Đằng (1288) | Mục: Diễn biến chiến sự]",
        "links": ["Trần Quốc Tuấn", "Đại Việt", "nhà Nguyên", "Ô Mã Nhi", "sông Bạch Đằng"],
        "era_id": "phongkien",
    }
    entities = [
        {"name": "Trần Quốc Tuấn", "type": "Person"},
        {"name": "Đại Việt", "type": "Polity"},
        {"name": "nhà Nguyên", "type": "Polity"},
        {"name": "Ô Mã Nhi", "type": "Person"},
        {"name": "Trận Bạch Đằng (1288)", "type": "Event"},
        {"name": "sông Bạch Đằng", "type": "Place"},
    ]
    period = {
        "name": "Nhà Trần",
        "era_id": "phongkien",
        "role_vocab": ["quốc công tiết chế", "thượng tướng", "hoàng đế"],
        "polities": ["Đại Việt", "Nhà Nguyên"],
    }

    def estimate_tokens(text: str) -> int:
        words = len(text.split())
        chars = len(text)
        return int(max(words * 1.3, chars / 3.0))

    # 1. Đoán Pass 1
    ent_msgs = build_entity_messages(chunk, period=period)
    total_ent_text = " ".join(m["content"] for m in ent_msgs)
    est_ent_tokens = estimate_tokens(total_ent_text)

    # 2. Đoán Pass 2
    rel_msgs = build_relation_messages(chunk, entities=entities, period=period)
    total_rel_text = " ".join(m["content"] for m in rel_msgs)
    est_rel_tokens = estimate_tokens(total_rel_text)

    # Khẳng định cả hai pass đều nằm gọn dưới ngưỡng 3000 token (ngưỡng an toàn cho mô hình 4B num_ctx=8192)
    assert est_ent_tokens < 3000, f"Pass 1 quá dài: {est_ent_tokens} tokens"
    assert est_rel_tokens < 3000, f"Pass 2 quá dài: {est_rel_tokens} tokens"

    # In ra để xác thực: thường chỉ khoảng 800 - 1400 tokens
    assert est_ent_tokens < 1800
    assert est_rel_tokens < 1800
