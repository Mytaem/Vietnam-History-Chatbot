"""Chọn bài theo profile: seed + category + 1-hop → lọc P31/năm/1945 → gán period, tier. (M3)"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from hgr.config import CONFIG_DIR, get_settings
from hgr.ingest.wiki_client import WikiClient
from hgr.ingest.wikidata_client import WikidataClient, year_range
from hgr.log import get_logger
from hgr.periods import Period, all_periods, overlaps
from hgr.process.normalize import nfc, normalize_text, parse_time
from hgr.process.parser import parse_article

log = get_logger(__name__)

_NON_ARTICLE = re.compile(r"^(?:Năm\s+)?\d+(?:\s+TCN)?$|^Thế kỷ\s|^Thập niên\s|^Danh sách\s", re.IGNORECASE)


def resolve_profile(profile: str) -> tuple[str, list[Period]]:
    """'mini' | 'core' | 'full' | 'era:<id>' | 'period:<id>' → (loại, các period mục tiêu)."""
    kind, _, arg = profile.partition(":")
    periods = all_periods()
    if kind in ("mini", "core", "full") and not arg:
        return kind, periods
    if kind == "era":
        targets = [p for p in periods if p.era_id == arg]
    elif kind == "period":
        targets = [p for p in periods if p.id == arg]
    else:
        targets = []
    if not targets:
        raise ValueError(f"Profile không hợp lệ: {profile!r}")
    return kind, targets


def _overlap_len(p: Period, start: int, end: int) -> int:
    return max(0, min(p.end, end) - max(p.start, start) + 1)


def assign_period(article: dict, scope: set[str] | None = None) -> tuple[str | None, list[str]]:
    """→ (period_id chính, period_ids giao nhau).

    Ưu tiên: period của seed → period gợi ý (bài seed trỏ tới) có giao năm → period trục chính trong
    phạm vi profile giao năm nhiều nhất (hòa thì chọn period hẹp hơn) → period gợi ý đầu tiên.
    Nhánh song song (Chăm Pa…) dài hàng thế kỷ nên chỉ được chọn khi có gợi ý hoặc không còn lựa chọn khác.
    """
    periods = all_periods()
    start, end = article.get("start_year"), article.get("end_year")
    overlapping = [p for p in periods if start is not None and overlaps(p.start, p.end, start, end)]
    primary = article.get("seed_period")
    hints = article.get("hint_periods") or []

    if primary is None and overlapping:
        in_scope = [p for p in overlapping if scope is None or p.id in scope]
        main_line = [p for p in in_scope if not p.parallel]
        hinted = [p for p in overlapping if p.id in hints]
        pool = [p for p in hinted if not p.parallel] or hinted or main_line or in_scope or overlapping
        best = max(pool, key=lambda p: (_overlap_len(p, start, end if end is not None else start), p.start - p.end))
        primary = best.id
    if primary is None and hints:
        primary = hints[0]

    ids = [p.id for p in overlapping]
    if primary is not None and primary not in ids:
        ids.insert(0, primary)
    return primary, ids


def assign_tier(articles: list[dict], quota: int) -> None:
    """Seed trước (theo thứ tự trong periods.yaml), còn thiếu lấy bài có năm và nhiều liên kết → tier A, còn lại B."""
    ranked = sorted(
        articles,
        key=lambda a: (not a.get("is_seed"), a.get("seed_rank", 0), a.get("start_year") is None,
                       -(a.get("in_links", 0) + a.get("seed_links", 0)), a["title"]),
    )
    for i, article in enumerate(ranked):
        article["tier"] = "A" if i < quota else "B"


def _rank_hints(hints: Counter) -> list[str]:
    """Giai đoạn gợi ý xếp theo số seed link tới (nhiều trước); hòa thì trục chính trước nhánh song song."""
    parallel = {p.id for p in all_periods() if p.parallel}
    return sorted(hints, key=lambda pid: (-hints[pid], pid in parallel, pid))


def _load_seeds() -> dict:
    with open(CONFIG_DIR / "seeds.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _period_caps(kind: str, targets: list[Period], max_articles: dict) -> dict[str, int]:
    """Số bài tối đa mỗi period: mini/core = quota, period/era/full chia max_articles theo quota."""
    if kind in ("mini", "core"):
        return {p.id: p.tier_a_quota for p in targets}
    total = max_articles[kind]
    quota_sum = sum(p.tier_a_quota for p in targets) or 1
    return {p.id: max(p.tier_a_quota, round(total * p.tier_a_quota / quota_sum)) for p in targets}


_PAREN = re.compile(r"\(([^()]{1,120})\)")


def _text_years(article: dict) -> tuple[int | None, int | None]:
    """Năm trong ngoặc đơn của câu mở đầu, vd "Ngô Quyền (897 – 944)", khi Wikidata không có.

    Chỉ đọc trong ngoặc vì phần còn lại của câu mở đầu hay chứa năm phát hiện/xuất bản (di chỉ, sách).
    """
    parsed = article.get("_parsed") or {}
    lead = next((s["text"] for s in parsed.get("sections", []) if s["path"] == "Mở đầu"), "")
    first_sentence = lead.split(". ", 1)[0][:300]
    for m in _PAREN.finditer(first_sentence):
        spans = parse_time(m.group(1))
        if spans:
            return _valid_years(min(s.start for s in spans), max(s.end for s in spans))
    return None, None


def _valid_years(start: int | None, end: int | None) -> tuple[int | None, int | None]:
    """Bỏ khoảng năm vô lý (vd Wikidata ghi năm TCN thiếu dấu âm → đầu > cuối)."""
    if start is None or (end is not None and start > end):
        return None, None
    return start, end


def _too_young(entity: dict, max_year: int, min_age: int) -> bool:
    births = [b[0] for b in entity["times"].get("P569", [])]
    return "Q5" in entity["p31"] and bool(births) and min(births) > max_year - min_age


_INITIALS = re.compile(r"^(?:[^\W\d_]{1,2}\.\s*)+[^\W\d_]{0,3}\.?$")


def _useful_alias(alias: str, title: str) -> bool:
    """Bỏ alias gây gộp nhầm thực thể: quá ngắn ("Lin", "N."), chữ viết tắt ("T.L.", "N.A.Q"), chuỗi hỏng."""
    letters = re.sub(r"[\W\d_]", "", alias)
    return (
        len(letters) >= 4
        and not _INITIALS.match(alias)
        and "|" not in alias
        and len(alias) <= 80
        and alias.casefold() != title.casefold()
    )


def _entity_fields(entity: dict | None, title: str = "") -> dict:
    if not entity:
        return {"label": None, "aliases": [], "description": None, "p31": [], "wikidata": {}}
    aliases = [a for lang in ("vi", "en") for a in entity["aliases"].get(lang, [])]
    aliases += [entity["labels"][lang] for lang in ("en",) if lang in entity["labels"]]
    aliases = [" ".join(normalize_text(a).split()) for a in aliases]
    return {
        "label": entity["labels"].get("vi") or entity["labels"].get("en"),
        "aliases": list(dict.fromkeys(a for a in aliases if _useful_alias(a, title))),
        "description": entity["descriptions"].get("vi") or entity["descriptions"].get("en"),
        "p31": entity["p31"],
        "wikidata": {"times": entity["times"], "rels": entity["rels"]},
    }


def collect(profile: str, fresh: bool = False) -> dict:
    """Ghi data/raw/<period_id>/articles.jsonl và data/reports/missing_seeds.txt. Trả về thống kê.

    Mặc định gộp với dữ liệu đã có (bài trùng page_id được cập nhật); `fresh=True` xóa data/raw trước.
    """
    settings = get_settings()
    cfg = settings.ingest
    max_year = settings.scope.max_year
    kind, targets = resolve_profile(profile)
    target_ids = {p.id for p in targets}
    seeds_cfg = _load_seeds()
    blocklist = {nfc(t) for t in seeds_cfg.get("blocklist") or []}
    api_cache = Path(settings.project_root) / settings.paths.data_dir / "cache" / "api"
    wiki = WikiClient(cfg.user_agent, cache_dir=api_cache)
    wikidata = WikidataClient(cfg.user_agent, batch=cfg.wikidata_batch, cache_dir=api_cache)

    # 1. Seed: tiêu đề → period khai báo
    seed_titles: dict[str, str | None] = {}
    period_of_title = {nfc(t): p.id for p in all_periods() for t in p.seed_titles}
    if kind == "mini":
        for title in seeds_cfg.get("mini") or []:
            seed_titles[nfc(title)] = period_of_title.get(nfc(title))
    else:
        for p in targets:
            for title in p.seed_titles:
                seed_titles.setdefault(nfc(title), p.id)
    for extra in seeds_cfg.get("extra") or []:
        if kind == "mini" or extra.get("period") in target_ids:
            seed_titles[nfc(extra["title"])] = extra.get("period")
    for title in list(seed_titles):
        if title in blocklist:
            del seed_titles[title]

    log.info("Profile %s: %d period, %d tiêu đề seed", profile, len(targets), len(seed_titles))
    fetched = wiki.fetch_pages(list(seed_titles))
    missing = [(p["title"], seed_titles.get(p["title"])) for p in fetched if p.get("missing")]
    articles: dict[str, dict] = {}
    seed_order = {title: i for i, title in enumerate(seed_titles)}
    for page in (p for p in fetched if not p.get("missing")):
        page["is_seed"] = True
        # Thứ tự trong periods.yaml là thứ tự quan trọng (API trả về theo thứ tự khác).
        page["seed_rank"] = min(seed_order.get(r, len(seed_order)) for r in page["requested"])
        page["seed_period"] = next((seed_titles[r] for r in page["requested"] if seed_titles.get(r)), None)
        page["seed_period"] = page["seed_period"] or period_of_title.get(page["title"])
        page["in_links"] = 0
        page["_parsed"] = parse_article(page["wikitext"] or "", settings.chunk.drop_sections)
        articles[page["title"]] = page

    # 2. Mở rộng (trừ mini): thể loại + link 1 bước từ bài seed
    expansion: dict[str, dict] = defaultdict(lambda: {"hints": Counter(), "in_links": 0})
    if kind != "mini":
        for p in targets:
            for category in p.seed_categories:
                for title in wiki.category_members(category, cfg.category_depth):
                    expansion[title]["hints"][p.id] += 1
        if cfg.expand_hops >= 1:
            for page in articles.values():
                for target in dict.fromkeys(link["target"] for link in page["_parsed"]["links"]):
                    info = expansion[target]
                    info["in_links"] += 1
                    if page["seed_period"]:
                        info["hints"][page["seed_period"]] += 1
        for title in list(expansion):
            if title in articles or title in blocklist or _NON_ARTICLE.search(title):
                del expansion[title]
    log.info("Ứng viên mở rộng: %d", len(expansion))

    # 3. Wikidata cho seed + ứng viên (chưa tải nội dung ứng viên)
    candidates = [p for p in wiki.fetch_pages(list(expansion), content=False) if not p.get("missing")]
    entities = wikidata.get_entities(
        [a["qid"] for a in articles.values()] + [c["qid"] for c in candidates]
    )

    allowed_p31 = set(cfg.allowed_p31)
    kept: dict[str, dict] = {}
    rejected_p31: list[tuple[int, str, list[str]]] = []
    too_young: list[str] = []
    for page in candidates:
        if page["title"] in articles or page["title"] in kept:
            continue
        entity = entities.get(page["qid"])
        if not entity:
            continue
        if not allowed_p31 & set(entity["p31"]):
            in_links = sum(expansion[r]["in_links"] for r in page["requested"])
            rejected_p31.append((in_links, page["title"], entity["p31"]))
            continue
        if _too_young(entity, max_year, cfg.person_min_age_1945):
            too_young.append(page["title"])
            continue
        start, end = _valid_years(*year_range(entity))
        if start is not None and (start > max_year or not any(overlaps(p.start, p.end, start, end) for p in targets)):
            continue
        hints: Counter = Counter()
        in_links = 0
        for requested in page["requested"]:
            in_links += expansion[requested]["in_links"]
            hints.update(expansion[requested]["hints"])
        page.update(is_seed=False, seed_period=None, start_year=start, end_year=end, in_links=in_links,
                    hint_periods=_rank_hints(hints))
        page["period_id"], _ = assign_period(page, target_ids)
        if page["period_id"] in target_ids:
            kept[page["title"]] = page

    # 4. Tải nội dung ứng viên, bỏ bài lạc đề (không link tới bài seed nào), rồi mới giới hạn theo quota
    seed_names = {normalize_text(t) for a in articles.values() for t in [a["title"], *a["requested"], *a["redirects"]]}
    off_topic: list[str] = []
    if kept:
        contents = {p["title"]: p for p in wiki.fetch_pages(list(kept)) if not p.get("missing")}
        for title, page in list(kept.items()):
            if title not in contents:
                del kept[title]
                continue
            page["wikitext"] = contents[title]["wikitext"]
            page["_parsed"] = parse_article(page["wikitext"] or "", settings.chunk.drop_sections)
            page["seed_links"] = len({link["target"] for link in page["_parsed"]["links"]} & seed_names)
            if page["seed_links"] < cfg.min_seed_links:
                off_topic.append(title)
                del kept[title]
    log.info("Ứng viên sau lọc P31/năm/độ liên quan: %d (lạc đề: %d)", len(kept), len(off_topic))

    caps = _period_caps(kind, targets, dict(cfg.max_articles))
    seeds_per_period: dict[str, int] = defaultdict(int)
    for page in articles.values():
        seeds_per_period[page["seed_period"]] += 1
    by_period: dict[str, list[dict]] = defaultdict(list)
    for page in kept.values():
        by_period[page["period_id"]].append(page)
    chosen = []
    for period_id, pages in by_period.items():
        room = max(0, caps.get(period_id, 0) - seeds_per_period[period_id])
        pages.sort(key=lambda a: (-(a["in_links"] + a["seed_links"]), a["title"]))
        chosen += pages[:room]
    for page in chosen:
        articles[page["title"]] = page

    # 5. Năm, lọc mốc 1945, gán period + tier
    dropped_after_cutoff, dropped_out_of_scope = [], []
    for title, page in list(articles.items()):
        page.update(_entity_fields(entities.get(page["qid"]), page["title"]))
        if page.get("start_year") is None:
            start, end = _valid_years(*year_range(entities[page["qid"]])) if page["qid"] in entities else (None, None)
            source = "wikidata"
            if start is None:
                start, end = _text_years(page)
                source = "text" if start is not None else None
            page.update(start_year=start, end_year=end, year_source=source)
        else:
            page.setdefault("year_source", "wikidata")
        if page["start_year"] is not None and page["start_year"] > max_year:
            if page["is_seed"]:
                # Seed đã được chọn tay là thuộc phạm vi: năm >1945 là năm sai (vd QID trỏ nhầm phường mới lập).
                page.update(start_year=None, end_year=None, year_source=None)
            else:
                dropped_after_cutoff.append(title)
                del articles[title]
                continue
        page["period_id"], page["period_ids"] = assign_period(page, target_ids)
        if not page["is_seed"] and page["period_id"] not in target_ids:
            dropped_out_of_scope.append(title)
            del articles[title]

    grouped: dict[str, list[dict]] = defaultdict(list)
    unassigned = []
    for page in articles.values():
        if page["period_id"] is None:
            unassigned.append(page["title"])
        else:
            grouped[page["period_id"]].append(page)
    periods_by_id = {p.id: p for p in all_periods()}
    for period_id, pages in grouped.items():
        quota = len(pages) if kind == "mini" else periods_by_id[period_id].tier_a_quota
        assign_tier(pages, quota)
        if kind == "core":
            grouped[period_id] = [p for p in pages if p["tier"] == "A"]

    # 6. Tên cho các QID quan hệ (cha, mẹ, kế nhiệm…) để bước trích xuất có cạnh Wikidata dùng được ngay
    rel_qids = {q for pages in grouped.values() for p in pages for qs in p["wikidata"].get("rels", {}).values() for q in qs}
    rel_labels = wikidata.get_labels(sorted(rel_qids))
    for pages in grouped.values():
        for p in pages:
            rels = p["wikidata"].get("rels", {})
            p["wikidata"]["rel_labels"] = {q: rel_labels[q] for qs in rels.values() for q in qs if q in rel_labels}

    # 7. Ghi file: gộp với dữ liệu các lần chạy trước (bài chuyển giai đoạn được dời sang file mới)
    data_dir = Path(settings.project_root) / settings.paths.data_dir
    reports_dir = Path(settings.project_root) / settings.paths.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = data_dir / "raw"
    if fresh:
        for period_dir in (d for d in raw_dir.glob("*") if d.is_dir()):
            shutil.rmtree(period_dir)
    records: dict[int, dict] = {}
    for path in raw_dir.glob("*/articles.jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    records[record["page_id"]] = record
    for pages in grouped.values():
        for page in pages:
            records[page["page_id"]] = _record(page)
    by_period: dict[str, list[dict]] = defaultdict(list)
    for record in records.values():
        by_period[record["period_id"]].append(record)
    for path in raw_dir.glob("*/articles.jsonl"):
        if path.parent.name not in by_period:
            path.unlink()
    for period_id, rows in by_period.items():
        out = raw_dir / period_id / "articles.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for row in sorted(rows, key=lambda a: (a["tier"], not a["is_seed"], a["title"])):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (reports_dir / "missing_seeds.txt").write_text(
        "".join(f"{title}\t{period or ''}\n" for title, period in missing), encoding="utf-8"
    )
    (reports_dir / "rejected_p31.tsv").write_text(
        "in_links\ttitle\tp31\n"
        + "".join(f"{n}\t{t}\t{','.join(p31)}\n" for n, t, p31 in sorted(rejected_p31, reverse=True)),
        encoding="utf-8",
    )

    for title in unassigned:
        log.warning("Không gán được giai đoạn (thiếu năm): %s", title)
    return {
        "profile": profile,
        "articles": {pid: len(pages) for pid, pages in sorted(grouped.items())},
        "tier_a": sum(1 for pages in grouped.values() for p in pages if p["tier"] == "A"),
        "missing_seeds": missing,
        "dropped_after_cutoff": dropped_after_cutoff,
        "dropped_out_of_scope": dropped_out_of_scope,
        "off_topic": off_topic,
        "too_young": too_young,
        "unassigned": unassigned,
        "total_on_disk": {pid: len(rows) for pid, rows in sorted(by_period.items())},
    }


def _record(page: dict) -> dict:
    return {
        "page_id": page["page_id"],
        "title": page["title"],
        "url": page["url"],
        "revision_id": page["revision_id"],
        "qid": page["qid"],
        "redirects": page.get("redirects", []),
        "is_seed": page["is_seed"],
        "in_links": page.get("in_links", 0),
        "seed_links": page.get("seed_links", 0),
        "label": page.get("label"),
        "aliases": page.get("aliases", []),
        "description": page.get("description"),
        "p31": page.get("p31", []),
        "wikidata": page.get("wikidata", {}),
        "start_year": page.get("start_year"),
        "end_year": page.get("end_year"),
        "year_source": page.get("year_source"),
        "period_id": page["period_id"],
        "period_ids": page["period_ids"],
        "tier": page["tier"],
        "wikitext": page["wikitext"],
    }
