"""Context có cấu trúc: PHẠM VI | THỰC THỂ | QUAN HỆ | ĐƯỜNG LIÊN KẾT | DÒNG THỜI GIAN | NGUỒN. (M6)"""
from __future__ import annotations

from hgr.ingest.wiki_client import WikiClient
from hgr.periods import all_periods
from hgr.process.chunker import estimate_tokens

MAX_SOURCES = 8
MAX_ENTITIES = 12
MAX_RELATIONS = 25


def _fmt_year(y: int | None) -> str:
    if y is None:
        return "?"
    return f"{-y} TCN" if y < 0 else str(y)


def _entity_label(node: dict) -> str:
    name = node.get("display_name") or node.get("name") or node.get("id")
    flags = []
    if node.get("legendary"):
        flags.append("truyền thuyết")
    if node.get("disputed"):
        flags.append("mốc tranh luận")
    years = ""
    if node.get("start_year") is not None:
        years = f" ({_fmt_year(node['start_year'])}" + (
            f"–{_fmt_year(node['end_year'])})" if node.get("end_year") not in (None, node["start_year"]) else ")"
        )
    flag_str = f" [{', '.join(flags)}]" if flags else ""
    return f"{name}{years} — {node.get('type', 'Entity')}{flag_str}"


def _scope_line(result) -> str:
    plan = result.plan
    period_ids = list(dict.fromkeys((plan.periods if plan else []) or []))
    if not period_ids:
        return "Toàn bộ phạm vi dữ liệu (tiền sử – hết 1945)"
    periods = {p.id: p for p in all_periods()}
    parts = []
    for pid in period_ids:
        p = periods.get(pid)
        if p is None:
            continue
        parts.append(f"{p.name} ({_fmt_year(p.start)}–{_fmt_year(p.end)})")
    return "Giai đoạn: " + "; ".join(parts) if parts else "Toàn bộ phạm vi dữ liệu (tiền sử – hết 1945)"


def _relation_line(rel: dict, node_names: dict[str, str], citation_by_chunk: dict[str, int]) -> str:
    head = node_names.get(rel["source_id"], rel["source_id"])
    tail = node_names.get(rel["target_id"], rel["target_id"])
    details = [d for d in (rel.get("role"), _fmt_year(rel["start_year"]) if rel.get("start_year") else None) if d]
    detail_str = f"({', '.join(details)})" if details else ""
    cites = sorted({citation_by_chunk[c] for c in rel.get("evidence_chunk_ids", []) if c in citation_by_chunk})
    cite_str = " " + "".join(f"[{n}]" for n in cites) if cites else ""
    return f"{head} —{rel['type']}{detail_str}→ {tail}{cite_str}"


def build_context(result, max_tokens: int = 1200) -> tuple[str, list[dict]]:
    """→ (context text, citations[{n, title, section, url, quote}])"""
    sections = [f"### PHẠM VI\n{_scope_line(result)}"]

    node_names = {n["id"]: (n.get("display_name") or n.get("name") or n["id"]) for n in result.subgraph.get("nodes", [])}
    entities = result.subgraph.get("nodes", [])[:MAX_ENTITIES]
    if entities:
        sections.append("### THỰC THỂ\n" + "\n".join(f"- {_entity_label(n)}" for n in entities))

    citations: list[dict] = []
    citation_by_chunk: dict[str, int] = {}
    used_tokens = 0
    for chunk in result.top_chunks:
        if len(citations) >= MAX_SOURCES:
            break
        tokens = estimate_tokens(chunk.get("text", ""))
        if citations and used_tokens + tokens > max_tokens:
            break
        used_tokens += tokens
        n = len(citations) + 1
        citation_by_chunk[chunk["id"]] = n
        citations.append({
            "n": n,
            "title": chunk.get("page_title", ""),
            "section": chunk.get("section_path", ""),
            "url": WikiClient.url(chunk.get("page_title", "")),
            "quote": chunk.get("text", ""),
        })

    if result.triplets:
        lines = [_relation_line(r, node_names, citation_by_chunk) for r in result.triplets[:MAX_RELATIONS]]
        sections.append("### QUAN HỆ\n" + "\n".join(f"- {line}" for line in lines))

    if result.paths:
        path_lines = []
        for path in result.paths:
            names = [node_names.get(n["id"], n.get("display_name") or n.get("name") or n["id"]) for n in path["nodes"]]
            edge_labels = [e["type"] for e in path["edges"]]
            chain = names[0]
            for label, nxt in zip(edge_labels, names[1:]):
                chain += f" —{label}→ {nxt}"
            path_lines.append(f"- {chain}")
        sections.append("### ĐƯỜNG LIÊN KẾT\n" + "\n".join(path_lines))

    timeline = sorted(
        {(n["start_year"], node_names.get(n["id"], n.get("name"))) for n in entities if n.get("start_year") is not None}
    )
    if timeline:
        sections.append(
            "### DÒNG THỜI GIAN\n" + "\n".join(f"- {_fmt_year(year)}: {name}" for year, name in timeline)
        )

    if citations:
        # Dùng nguyên văn, KHÔNG cắt ngắn thêm ở đây: ngân sách max_tokens đã được áp đúng lúc chọn chunk ở
        # trên (theo token thật). Cắt cứng theo ký tự sẽ chặt ngang câu, thiếu đúng chi tiết quan trọng nhất
        # (vd "...thuộc địa phận [Hải Dương]" bị cắt mất [Hải Dương]) và khiến model tự đoán bừa chỗ thiếu.
        src_lines = [f'[{c["n"]}] ({c["title"]} › {c["section"]}) "{c["quote"]}"' for c in citations]
        sections.append("### NGUỒN\n" + "\n".join(src_lines))

    return "\n\n".join(sections), citations
