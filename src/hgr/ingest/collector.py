"""Chọn bài theo profile: seed + category + 1-hop → lọc P31/năm/1945 → gán period, tier. (M3)"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

from hgr.config import CONFIG_DIR, get_settings
from hgr.ingest.wiki_client import WikiClient
from hgr.ingest.wikidata_client import WikidataClient, year_range
from hgr.log import get_logger
from hgr.periods import Period, all_periods, overlaps
from hgr.process.normalize import nfc, parse_time
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
        pool = [p for p in overlapping if p.id in hints] or main_line or in_scope or overlapping
        best = max(pool, key=lambda p: (_overlap_len(p, start, end if end is not None else start), p.start - p.end))
        primary = best.id
    if primary is None and hints:
        primary = hints[0]

    ids = [p.id for p in overlapping]
    if primary is not None and primary not in ids:
        ids.insert(0, primary)
    return primary, ids


def assign_tier(articles: list[dict], quota: int) -> None:
    """Seed trước, còn thiếu lấy theo in-link → tier A, còn lại B."""
    ranked = sorted(
        articles,
        key=lambda a: (not a.get("is_seed"), a.get("seed_rank", 0), -a.get("in_links", 0), a["title"]),
    )
    for i, article in enumerate(ranked):
        article["tier"] = "A" if i < quota else "B"


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


def _text_years(article: dict) -> tuple[int | None, int | None]:
    """Năm lấy từ câu mở đầu (vd "Ngô Quyền (897 – 944)") khi Wikidata không có."""
    parsed = article.get("_parsed") or {}
    lead = next((s["text"] for s in parsed.get("sections", []) if s["path"] == "Mở đầu"), "")
    spans = parse_time(lead[:400])
    if not spans:
        return None, None
    return min(s.start for s in spans), max(s.end for s in spans)


def _entity_fields(entity: dict | None) -> dict:
    if not entity:
        return {"label": None, "aliases": [], "description": None, "p31": [], "wikidata": {}}
    aliases = [a for lang in ("vi", "en") for a in entity["aliases"].get(lang, [])]
    aliases += [entity["labels"][lang] for lang in ("en",) if lang in entity["labels"]]
    return {
        "label": entity["labels"].get("vi") or entity["labels"].get("en"),
        "aliases": list(dict.fromkeys(nfc(a) for a in aliases)),
        "description": entity["descriptions"].get("vi") or entity["descriptions"].get("en"),
        "p31": entity["p31"],
        "wikidata": {"times": entity["times"], "rels": entity["rels"]},
    }


def collect(profile: str) -> dict:
    """Ghi data/raw/<period_id>/articles.jsonl và data/reports/missing_seeds.txt. Trả về thống kê."""
    settings = get_settings()
    cfg = settings.ingest
    max_year = settings.scope.max_year
    kind, targets = resolve_profile(profile)
    target_ids = {p.id for p in targets}
    seeds_cfg = _load_seeds()
    blocklist = {nfc(t) for t in seeds_cfg.get("blocklist") or []}
    wiki = WikiClient(cfg.user_agent)
    wikidata = WikidataClient(cfg.user_agent, batch=cfg.wikidata_batch)

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
    for rank, page in enumerate(p for p in fetched if not p.get("missing")):
        page["is_seed"] = True
        page["seed_rank"] = rank
        page["seed_period"] = next((seed_titles[r] for r in page["requested"] if seed_titles.get(r)), None)
        page["seed_period"] = page["seed_period"] or period_of_title.get(page["title"])
        page["in_links"] = 0
        page["_parsed"] = parse_article(page["wikitext"] or "", settings.chunk.drop_sections)
        articles[page["title"]] = page

    # 2. Mở rộng (trừ mini): thể loại + link 1 bước từ bài seed
    expansion: dict[str, dict] = defaultdict(lambda: {"hint_periods": [], "in_links": 0})
    if kind != "mini":
        for p in targets:
            for category in p.seed_categories:
                for title in wiki.category_members(category, cfg.category_depth):
                    if p.id not in expansion[title]["hint_periods"]:
                        expansion[title]["hint_periods"].append(p.id)
        if cfg.expand_hops >= 1:
            for page in articles.values():
                for target in dict.fromkeys(link["target"] for link in page["_parsed"]["links"]):
                    info = expansion[target]
                    info["in_links"] += 1
                    if page["seed_period"] and page["seed_period"] not in info["hint_periods"]:
                        info["hint_periods"].append(page["seed_period"])
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
    for page in candidates:
        if page["title"] in articles or page["title"] in kept:
            continue
        entity = entities.get(page["qid"])
        if not entity or not allowed_p31 & set(entity["p31"]):
            continue
        start, end = year_range(entity)
        if start is not None and (start > max_year or not any(overlaps(p.start, p.end, start, end) for p in targets)):
            continue
        info = {"hint_periods": [], "in_links": 0}
        for requested in page["requested"]:
            info["in_links"] += expansion[requested]["in_links"]
            info["hint_periods"] += [h for h in expansion[requested]["hint_periods"] if h not in info["hint_periods"]]
        page.update(is_seed=False, seed_period=None, start_year=start, end_year=end, **info)
        page["period_id"], _ = assign_period(page, target_ids)
        if page["period_id"] in target_ids:
            kept[page["title"]] = page

    # 4. Giới hạn số bài mỗi period trước khi tải nội dung
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
        pages.sort(key=lambda a: (-a["in_links"], a["title"]))
        chosen += pages[:room]
    if chosen:
        contents = {p["title"]: p for p in wiki.fetch_pages([p["title"] for p in chosen]) if not p.get("missing")}
        for page in chosen:
            if page["title"] in contents:
                page["wikitext"] = contents[page["title"]]["wikitext"]
                page["_parsed"] = parse_article(page["wikitext"] or "", settings.chunk.drop_sections)
                articles[page["title"]] = page

    # 5. Năm, lọc mốc 1945, gán period + tier
    dropped_after_cutoff, dropped_out_of_scope = [], []
    for title, page in list(articles.items()):
        page.update(_entity_fields(entities.get(page["qid"])))
        if page.get("start_year") is None:
            start, end = year_range(entities[page["qid"]]) if page["qid"] in entities else (None, None)
            source = "wikidata"
            if start is None:
                start, end = _text_years(page)
                source = "text" if start is not None else None
            page.update(start_year=start, end_year=end, year_source=source)
        else:
            page.setdefault("year_source", "wikidata")
        if page["start_year"] is not None and page["start_year"] > max_year:
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

    # 6. Ghi file
    data_dir = Path(settings.project_root) / settings.paths.data_dir
    reports_dir = Path(settings.project_root) / settings.paths.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    for period_id, pages in grouped.items():
        out = data_dir / "raw" / period_id / "articles.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for page in sorted(pages, key=lambda a: (a["tier"], not a["is_seed"], a["title"])):
                f.write(json.dumps(_record(page), ensure_ascii=False) + "\n")
    (reports_dir / "missing_seeds.txt").write_text(
        "".join(f"{title}\t{period or ''}\n" for title, period in missing), encoding="utf-8"
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
        "unassigned": unassigned,
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
