"""Hợp nhất thực thể: link→QID → alias dict → fuzzy (blocking type + period) → local id. (M5)"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz

from hgr.config import get_settings


def _clean(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "")).strip()


def _slug(text: str) -> str:
    # Chuẩn hóa các dấu gạch ngang unicode (en-dash, em-dash, v.v.) và gạch dưới thành '-'
    text = re.sub(r"[\u2010-\u2015_]", "-", text or "")
    value = _clean(text).lower().replace("đ", "d")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9\s\-]", "", value)
    value = re.sub(r"[\s\-]+", "-", value).strip("-")
    return value or "entity"


class EntityResolver:
    """Bộ giải quyết và hợp nhất thực thể tri thức (Entity Resolution)."""

    def __init__(self, fuzzy_threshold: int | float = 92, event_year_tolerance: int = 1):
        # CẢNH BÁO: Công thức trung bình cộng (token_set + token_sort) / 2 KHÔNG an toàn nếu
        # threshold hạ xuống dưới khoảng 90 (dẫn chứng: "Lý Thường" vs "Lý Thường Kiệt" đạt trung bình 89.13,
        # sẽ bị gộp nhầm). Nếu cần hạ ngưỡng, bắt buộc phải kiểm tra lại bằng bộ tests/test_resolver.py trước.
        self.fuzzy_threshold = float(fuzzy_threshold)
        self.event_year_tolerance = int(event_year_tolerance)
        self.aliases: dict[str, set[str]] = {}
        self.alias_to_id: dict[str, str] = {}
        self.typed_alias_to_id: dict[tuple[str, str], str] = {}
        self.entity_type_by_id: dict[str, str] = {}
        self.entities_by_type: dict[str, list[dict]] = {}

    def add_aliases(self, canonical_id: str, names: list[str], ent_type: str | None = None) -> None:
        """Đăng ký danh sách tên gọi/alias cho một ID chuẩn hóa."""
        if not canonical_id:
            return
        self.aliases.setdefault(canonical_id, set())
        if ent_type and ent_type != "Unknown":
            self.entity_type_by_id[canonical_id] = ent_type

        for name in names:
            if not name:
                continue
            cleaned = _clean(name)
            if not cleaned:
                continue
            self.aliases[canonical_id].add(cleaned)
            norm_key = cleaned.casefold()
            self.alias_to_id.setdefault(norm_key, canonical_id)
            if ent_type and ent_type != "Unknown":
                self.typed_alias_to_id.setdefault((norm_key, ent_type), canonical_id)

        # Lưu candidate vào entities_by_type nếu có type để phục vụ fuzzy matching
        if ent_type and ent_type != "Unknown":
            type_list = self.entities_by_type.setdefault(ent_type, [])
            existing = next((e for e in type_list if e["id"] == canonical_id), None)
            if existing:
                existing["aliases"].update(self.aliases[canonical_id])
            else:
                first_name = names[0] if names else canonical_id
                type_list.append({
                    "id": canonical_id,
                    "name": _clean(first_name),
                    "type": ent_type,
                    "start_year": None,
                    "period_id": "",
                    "aliases": set(self.aliases[canonical_id]),
                })

    def load_dia_danh(self, path: Path | str) -> int:
        """Nạp địa danh lịch sử và tên thay thế từ dia_danh.yaml."""
        p = Path(path)
        if not p.exists():
            return 0
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        count = 0
        for place in data.get("dia_danh", []):
            cid = f"local:{place['id']}"
            names = [place.get("canonical", "")]
            names.extend(item.get("name", "") for item in place.get("names", []))
            self.add_aliases(cid, names, ent_type="Place")
            count += 1
        return count

    def load_backbone(self, backbone_dir: Path | str) -> int:
        """Nạp alias từ toàn bộ các bảng backbone trong configs/backbone/."""
        b_dir = Path(backbone_dir)
        if not b_dir.exists():
            return 0
        count = 0

        # 1. dia_danh.yaml (Place)
        dia_danh_p = b_dir / "dia_danh.yaml"
        if dia_danh_p.exists():
            count += self.load_dia_danh(dia_danh_p)

        # 2. trieu_dai.yaml (Polity)
        td_p = b_dir / "trieu_dai.yaml"
        if td_p.exists():
            td_data = yaml.safe_load(td_p.read_text(encoding="utf-8")) or {}
            for td in td_data.get("trieu_dai", []):
                name = td.get("name")
                if name:
                    cid = f"local:{_slug(name)}"
                    names = [name]
                    if td.get("aliases"):
                        names.extend(td["aliases"])
                    self.add_aliases(cid, names, ent_type="Polity")
                    count += 1

        # 3. quoc_hieu.yaml (Polity)
        qh_p = b_dir / "quoc_hieu.yaml"
        if qh_p.exists():
            qh_data = yaml.safe_load(qh_p.read_text(encoding="utf-8")) or {}
            for qh in qh_data.get("quoc_hieu", []):
                name = qh.get("name")
                if name:
                    cid = f"local:{_slug(name)}"
                    names = [name]
                    if qh.get("aliases"):
                        names.extend(qh["aliases"])
                    self.add_aliases(cid, names, ent_type="Polity")
                    count += 1

        # 4. kinh_do.yaml (Place & Polity)
        kd_p = b_dir / "kinh_do.yaml"
        if kd_p.exists():
            kd_data = yaml.safe_load(kd_p.read_text(encoding="utf-8")) or {}
            for kd in kd_data.get("kinh_do", []):
                place = kd.get("place")
                if place:
                    self.add_aliases(f"local:{_slug(place)}", [place], ent_type="Place")
                    count += 1

        # nien_hieu.yaml CHỦ Ý không đăng ký ở đây: niên hiệu (Gia Long, Minh Mạng, Quang Trung...) chính là
        # tên gọi phổ biến nhất của vị vua đó trong văn bản thật, không phải một Work riêng. Gán type="Work"
        # cho tên niên hiệu sẽ xung đột và làm hỏng entity Person của hầu hết vua Nguyễn/Tây Sơn (resolver
        # coi type xung đột là 2 thực thể khác nhau). File này chỉ dùng để quy đổi năm trong process/normalize.py.

        return count

    def load_periods(self, periods_path: Path | str) -> int:
        """Nạp alias cho các Period và Era từ periods.yaml."""
        p = Path(periods_path)
        if not p.exists():
            return 0
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        count = 0
        for era in data.get("eras", []):
            era_id = f"local:{era.get('id')}"
            names = [era.get("name", "")] + list(era.get("aliases", []))
            self.add_aliases(era_id, names)
            count += 1
            for per in era.get("periods", []):
                per_id = f"local:{per.get('id')}"
                p_names = [per.get("name", "")] + list(per.get("aliases", []))
                self.add_aliases(per_id, p_names)
                count += 1
        return count

    def load_articles(self, articles_source: Path | str | list[dict]) -> int:
        """Nạp alias và redirects từ dữ liệu Wikidata trong bài viết đã ingest."""
        articles = []
        if isinstance(articles_source, (str, Path)):
            p = Path(articles_source)
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            articles.append(json.loads(line))
                        except Exception:
                            continue
        elif isinstance(articles_source, list):
            articles = articles_source

        count = 0
        for art in articles:
            title = art.get("title")
            if not title:
                continue
            qid = art.get("qid")
            if qid:
                canonical_id = f"qid:{str(qid).removeprefix('qid:')}"
            else:
                canonical_id = f"local:{_slug(title)}"

            names = [title]
            if art.get("label"):
                names.append(art["label"])
            names.extend(art.get("aliases", []))
            names.extend(art.get("redirects", []))

            ent_type = art.get("type")
            self.add_aliases(canonical_id, names, ent_type=ent_type)
            count += 1
        return count

    def _fuzzy_match(
        self,
        name: str,
        ent_type: str,
        start_year: int | None,
        period_id: str = "",
    ) -> str | None:
        """So khớp fuzzy giữa các thực thể CÙNG type dùng kết hợp token_set_ratio và token_sort_ratio."""
        if not ent_type or ent_type == "Unknown":
            return None

        candidates = self.entities_by_type.get(ent_type, [])
        if not candidates:
            return None

        clean_name = _clean(name).casefold()
        best_score = 0.0
        best_candidate_id = None

        for cand in candidates:
            # Type có năm (Event): chỉ coi là khớp nếu cả hai bên có năm và chênh lệch <= event_year_tolerance
            if ent_type == "Event":
                cand_year = cand.get("start_year")
                # Nếu một trong hai bên thiếu năm, KHÔNG dùng fuzzy để gộp (an toàn hơn là tách riêng)
                if start_year is None or cand_year is None:
                    continue
                if abs(start_year - cand_year) > self.event_year_tolerance:
                    continue

            # So khớp chuỗi: kết hợp token_set_ratio (cho phép tiền tố/hư từ) và token_sort_ratio (phạt bỏ sót từ)
            names_to_compare = [cand["name"]] + list(cand.get("aliases", []))
            for cand_name in names_to_compare:
                if not cand_name:
                    continue
                c_name = _clean(cand_name).casefold()
                score_set = fuzz.token_set_ratio(clean_name, c_name)
                score_sort = fuzz.token_sort_ratio(clean_name, c_name)
                score = (score_set + score_sort) / 2.0
                if score >= self.fuzzy_threshold and score > best_score:
                    best_score = score
                    best_candidate_id = cand["id"]

        return best_candidate_id

    def _register_known_entity(
        self,
        entity_id: str,
        name: str,
        ent_type: str,
        start_year: int | None,
        period_id: str = "",
        aliases: list[str] | None = None,
    ) -> None:
        clean_name = _clean(name)
        norm_key = clean_name.casefold() if clean_name else ""

        # Đối với Event có năm, không ghi đè tên trần không có năm vào alias_to_id chung
        # để các sự kiện cùng tên khác năm hoặc không rõ năm không bị nuốt chửng
        is_event_with_year = (ent_type == "Event" and start_year is not None)

        if not is_event_with_year and norm_key:
            self.alias_to_id.setdefault(norm_key, entity_id)

        all_aliases = set(aliases or [])
        if clean_name:
            all_aliases.add(clean_name)

        if ent_type and ent_type != "Unknown":
            self.entity_type_by_id[entity_id] = ent_type
            if norm_key and not is_event_with_year:
                self.typed_alias_to_id.setdefault((norm_key, ent_type), entity_id)

        for a in all_aliases:
            if not a:
                continue
            ca = _clean(a)
            if ca:
                self.aliases.setdefault(entity_id, set()).add(ca)
                ak = ca.casefold()
                if not is_event_with_year:
                    self.alias_to_id.setdefault(ak, entity_id)
                    if ent_type and ent_type != "Unknown":
                        self.typed_alias_to_id.setdefault((ak, ent_type), entity_id)

        if ent_type and ent_type != "Unknown":
            self.entities_by_type.setdefault(ent_type, []).append({
                "id": entity_id,
                "name": clean_name,
                "type": ent_type,
                "start_year": start_year,
                "period_id": period_id,
                "aliases": all_aliases,
            })

    def resolve(self, entity: dict, chunk_links: list[dict] | None = None, period_id: str = "") -> str:
        """→ canonical id (qid:Qxxx | local:<slug> | local:<slug>-<năm>)."""
        chunk_links = chunk_links or []

        # 1. Có QID Wikidata -> id = "qid:Q<số>" (ưu tiên cao nhất, không qua fuzzy)
        qid = entity.get("qid")
        if qid:
            return f"qid:{str(qid).removeprefix('qid:')}"

        name = _clean(str(entity.get("name") or entity.get("head") or ""))
        if not name:
            return "local:unknown"

        ent_type = entity.get("type") or "Unknown"
        start_year = entity.get("start_year")
        try:
            start_year = int(start_year) if start_year is not None else None
        except (ValueError, TypeError):
            start_year = None

        # 2. Khớp chính xác qua alias dict (trỏ thẳng tới ID chuẩn, không qua fuzzy)
        # 2a. Kiểm tra typed alias trước nếu đã biết ent_type
        if ent_type != "Unknown":
            typed_id = self.typed_alias_to_id.get((name.casefold(), ent_type))
            if typed_id:
                if ent_type == "Event":
                    if typed_id.startswith("qid:"):
                        return typed_id
                    has_year = bool(re.search(r"-\d+$", typed_id))
                    if start_year is not None:
                        if typed_id.endswith(f"-{start_year}"):
                            return typed_id
                    else:
                        if not has_year:
                            return typed_id
                else:
                    return typed_id

        # 2b. Kiểm tra alias_to_id chung
        canonical_id = self.alias_to_id.get(name.casefold())
        if canonical_id:
            cand_type = self.entity_type_by_id.get(canonical_id)
            if ent_type != "Unknown" and cand_type and cand_type != "Unknown" and cand_type != ent_type:
                canonical_id = None
            elif ent_type == "Event":
                if not canonical_id.startswith("qid:"):
                    has_year = bool(re.search(r"-\d+$", canonical_id))
                    if start_year is not None:
                        if not canonical_id.endswith(f"-{start_year}"):
                            canonical_id = None
                    else:
                        if has_year:
                            canonical_id = None
        if canonical_id:
            return canonical_id

        # 3. Khớp chính xác với chunk_links
        for link in chunk_links:
            target = link if isinstance(link, str) else link.get("target")
            if not target:
                continue
            clean_target = _clean(target)
            if clean_target.casefold() == name.casefold():
                link_qid = link.get("qid") if isinstance(link, dict) else None
                if link_qid:
                    return f"qid:{str(link_qid).removeprefix('qid:')}"
                target_cid = self.alias_to_id.get(clean_target.casefold())
                if target_cid:
                    return target_cid
                if ent_type == "Event" and start_year is not None:
                    return f"local:{_slug(clean_target)}-{start_year}"
                return f"local:{_slug(clean_target)}"

        # 4. Fuzzy matching có điều kiện với các thực thể đã biết cùng type
        matched_id = self._fuzzy_match(name=name, ent_type=ent_type, start_year=start_year, period_id=period_id)
        if matched_id:
            norm_k = name.casefold()
            is_event_with_year = (ent_type == "Event" and start_year is not None)
            if not is_event_with_year:
                self.alias_to_id[norm_k] = matched_id
                if ent_type != "Unknown":
                    self.typed_alias_to_id[(norm_k, ent_type)] = matched_id
            if ent_type != "Unknown":
                self.entity_type_by_id[matched_id] = ent_type
            return matched_id

        # 5. Sinh ID mới (không khớp qua QID, Alias, ChunkLink, Fuzzy)
        if ent_type == "Event" and start_year is not None:
            new_id = f"local:{_slug(name)}-{start_year}"
        else:
            base_slug = _slug(name)
            existing_type = self.entity_type_by_id.get(f"local:{base_slug}")
            if existing_type and ent_type != "Unknown" and existing_type != "Unknown" and existing_type != ent_type:
                new_id = f"local:{base_slug}-{ent_type.lower()}"
            else:
                new_id = f"local:{base_slug}"

        self._register_known_entity(
            entity_id=new_id,
            name=name,
            ent_type=ent_type,
            start_year=start_year,
            period_id=period_id,
            aliases=entity.get("aliases", []),
        )
        return new_id


def run(
    extracted_dir: Path | str | None = None,
    resolved_dir: Path | str | None = None,
    processed_dir: Path | str | None = None,
) -> None:
    """extractions + structured → data/resolved/entities.jsonl, relations.jsonl, mentions.jsonl."""
    settings = get_settings()
    project_root = Path(settings.project_root)
    extracted_dir = Path(extracted_dir) if extracted_dir else project_root / settings.paths.data_dir / "extracted"
    resolved_dir = Path(resolved_dir) if resolved_dir else project_root / settings.paths.data_dir / "resolved"
    processed_dir = Path(processed_dir) if processed_dir else project_root / settings.paths.data_dir / "processed"
    resolved_dir.mkdir(parents=True, exist_ok=True)


    resolver = EntityResolver(settings.resolve.fuzzy_threshold, settings.resolve.event_year_tolerance)

    # 1. Nạp alias từ các bảng backbone
    backbone_dir = project_root / settings.scope.backbone_dir
    resolver.load_backbone(backbone_dir)
    periods_path = project_root / settings.scope.periods_file
    if periods_path.exists():
        resolver.load_periods(periods_path)

    # 2. Nạp alias từ bài viết ingest (processed/articles.jsonl hoặc raw/*/articles.jsonl)
    articles_path = processed_dir / "articles.jsonl"
    if articles_path.exists():
        resolver.load_articles(articles_path)
    else:
        # raw/ nằm cạnh processed/ được truyền vào, không phải data/ của dự án (test cô lập, nhiều bộ dữ liệu).
        for raw_path in sorted((processed_dir.parent / "raw").glob("*/articles.jsonl")):
            resolver.load_articles(raw_path)

    article_by_name: dict[str, dict] = {}
    chunks_path = processed_dir / "chunks.jsonl"
    if chunks_path.exists():
        for line in chunks_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                chunk = json.loads(line)
                title = chunk.get("page_title") or chunk.get("title")
                if title:
                    article_by_name[title.casefold()] = {
                        "qid": chunk.get("qid"),
                        "page_id": chunk.get("page_id"),
                        "period_ids": chunk.get("period_ids") or [chunk.get("period_id")],
                    }

    entity_by_id: dict[str, dict] = {}
    relation_rows: list[dict] = []
    mention_pairs: set[tuple[str, str]] = set()

    def register_entity(name: str, entity: dict | None = None, period_ids: list[str] | None = None) -> str:
        entity = entity or {}
        known_article = article_by_name.get(name.casefold(), {})
        qid = entity.get("qid") or known_article.get("qid")
        # Backbone (trieu_dai/quoc_hieu/kinh_do/dia_danh.yaml) đã biết type chắc chắn cho tên này: luôn ưu
        # tiên hơn type đoán từ domain/range của Tier S hoặc type do LLM gán lệch. Thiếu bước này, "Nhà Trần"
        # (Polity, từ backbone) và "Nhà Trần" (Person, đoán sai từ domain[0] của PARTICIPATED_IN/SUCCEEDED đa
        # domain) bị resolver coi là 2 thực thể khác nhau (type xung đột) và tạo 2 id riêng cho cùng một tên.
        known_type = resolver.entity_type_by_id.get(resolver.alias_to_id.get(_clean(name).casefold()))
        ent_type = known_type or entity.get("type")
        ent_payload = {
            "name": name,
            "qid": qid,
            "type": ent_type,
            "start_year": entity.get("start_year"),
            "end_year": entity.get("end_year"),
            "aliases": entity.get("aliases", []),
        }
        entity_id = resolver.resolve(ent_payload, [], period_ids[0] if period_ids else "")
        row = entity_by_id.setdefault(entity_id, {
            "id": entity_id,
            "qid": qid,
            "name": name,
            "aliases": [],
            "type": ent_type or "Unknown",
            "description": entity.get("description", ""),
            "period_ids": [],
            "start_year": entity.get("start_year"),
            "end_year": entity.get("end_year"),
        })
        for alias in [name, *entity.get("aliases", [])]:
            if alias and alias not in row["aliases"]:
                row["aliases"].append(alias)
        if row["type"] == "Unknown" and ent_type:
            row["type"] = ent_type
        for period_id in period_ids or known_article.get("period_ids", []):
            if period_id and period_id not in row["period_ids"]:
                row["period_ids"].append(period_id)
        for field in ("start_year", "end_year"):
            if row[field] is None and entity.get(field) is not None:
                row[field] = entity[field]
        return entity_id

    chunks_by_id: dict[str, dict] = {}
    if chunks_path.exists():
        for line in chunks_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                chunk = json.loads(line)
                chunks_by_id[chunk["id"]] = chunk

    # Tier S (backbone/Wikidata/infobox, confidence 0.95+) PHẢI được nạp trước Tier A/B (LLM, confidence thấp
    # hơn và có thể hallucinate). register_entity() chỉ điền start_year/end_year/type khi field còn trống
    # (first-wins), nên nếu LLM chạy trước và đoán sai (vd gán "Trận Bạch Đằng (1288)" thành năm 1945), giá
    # trị đúng 1288 từ Wikidata chạy sau sẽ không bao giờ ghi đè được nữa.
    # domain/range thật của từng quan hệ (vd CHILD_OF: Person→Person, OCCURRED_AT: Event→Place), để không
    # gán cứng mọi head/tail của Tier S thành "Polity" — sẽ mistype hầu hết Person (CHILD_OF, SPOUSE_OF,
    # RULED, PARTICIPATED_IN...) mỗi khi họ chưa được LLM trích xuất từ trước.
    from hgr.extract.validator import load_ontology

    relation_domain_range = load_ontology()["relations"]

    structured = extracted_dir / "structured.jsonl"
    if structured.exists():
        for line in structured.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            trip = json.loads(line)
            head = str(trip.get("head") or "")
            tail = str(trip.get("tail") or "")
            if not head or not tail:
                continue
            spec = relation_domain_range.get(trip.get("relation"), {})
            head_type = (spec.get("domain") or ["Unknown"])[0]
            tail_type = (spec.get("range") or ["Unknown"])[0]
            # start_year/end_year của triplet là năm của BÀI VIẾT CHỦ THỂ, chỉ thuộc về head hoặc tail
            # (đánh dấu ở year_target bởi structured_seed.py), không phải cả hai — nếu gán cho bên kia sẽ
            # thành sai năm sinh/mất của vợ/cha/người kế nhiệm... (dùng nhầm năm của chủ thể).
            years = {"start_year": trip.get("start_year"), "end_year": trip.get("end_year")}
            head_years = years if trip.get("year_target") == "head" else {}
            tail_years = years if trip.get("year_target") == "tail" else {}
            head_id = register_entity(head, {"type": head_type, **head_years})
            tail_id = register_entity(tail, {"type": tail_type, **tail_years})
            relation_rows.append({
                "id": f"rel:{head_id}:{trip.get('relation', 'RELATED_TO')}:{tail_id}",
                "head_id": head_id,
                "head": head,
                "relation": trip.get("relation", "RELATED_TO"),
                "tail_id": tail_id,
                "tail": tail,
                "start_year": trip.get("start_year"),
                "end_year": trip.get("end_year"),
                "confidence": trip.get("confidence", 1.0),
                "evidence": trip.get("evidence", ""),
                "source": "curated",
            })

    source = extracted_dir / "extractions.jsonl"
    if source.exists():
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            cid = item.get("chunk_id")
            chunk = chunks_by_id.get(cid, {})
            period_ids = chunk.get("period_ids") or [chunk.get("period_id")]
            entity_ids: dict[str, str] = {}
            for ent in item.get("entities", []):
                name = ent.get("name")
                if name:
                    eid = register_entity(name, ent, period_ids)
                    entity_ids[name] = eid
                    if cid and eid:
                        mention_pairs.add((str(cid), str(eid)))
            for trip in item.get("triplets", []):
                head = str(trip.get("head") or chunk.get("page_title") or "")
                tail = str(trip.get("tail") or "")
                if not head or not tail:
                    continue
                head_id = entity_ids.get(head) or register_entity(
                    head,
                    {
                        "qid": chunk.get("qid") if head == chunk.get("page_title") else None,
                        "type": "Unknown",
                        "start_year": trip.get("start_year"),
                        "end_year": trip.get("end_year"),
                    },
                    period_ids,
                )
                tail_id = entity_ids.get(tail) or register_entity(
                    tail,
                    {
                        "type": "Unknown",
                        "start_year": trip.get("start_year"),
                        "end_year": trip.get("end_year"),
                    },
                    period_ids=period_ids,
                )
                if cid and head_id:
                    mention_pairs.add((str(cid), str(head_id)))
                if cid and tail_id:
                    mention_pairs.add((str(cid), str(tail_id)))
                relation_rows.append({
                    "id": f"rel:{head_id}:{trip.get('relation', 'RELATED_TO')}:{tail_id}",
                    "head_id": head_id,
                    "head": head,
                    "relation": trip.get("relation", "RELATED_TO"),
                    "tail_id": tail_id,
                    "tail": tail,
                    "start_year": trip.get("start_year"),
                    "end_year": trip.get("end_year"),
                    "confidence": trip.get("confidence", 0.7),
                    "evidence": trip.get("evidence", ""),
                    "source": "extraction",
                })

    out_entities = resolved_dir / "entities.jsonl"
    with out_entities.open("w", encoding="utf-8") as f:
        for row in entity_by_id.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    out_rel = resolved_dir / "relations.jsonl"
    with out_rel.open("w", encoding="utf-8") as f:
        for row in relation_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    out_mentions = resolved_dir / "mentions.jsonl"
    with out_mentions.open("w", encoding="utf-8") as f:
        for cid, eid in sorted(mention_pairs):
            f.write(json.dumps({"chunk_id": cid, "entity_id": eid}, ensure_ascii=False) + "\n")

    try:
        e_rel = out_entities.relative_to(project_root)
        r_rel = out_rel.relative_to(project_root)
        m_rel = out_mentions.relative_to(project_root)
    except ValueError:
        e_rel, r_rel, m_rel = out_entities, out_rel, out_mentions

    print(f"[OK] {len(entity_by_id)} entity → {e_rel}")
    print(f"[OK] {len(relation_rows)} relation → {r_rel}")
    print(f"[OK] {len(mention_pairs)} mention → {m_rel}")

