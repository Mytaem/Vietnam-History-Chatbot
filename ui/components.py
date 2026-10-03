"""Thành phần giao diện dùng chung: thẻ, thông tin chính, nguồn, sơ đồ, khung ngữ cảnh."""
from __future__ import annotations

import html

import streamlit as st
from api import ApiUnavailable, entity_detail, entity_passages, periods_tree
from streamlit_agraph import Config, Edge, Node, agraph
from theme import (
    RELATION_VI,
    TYPE_COLOR,
    TYPE_ICON,
    TYPE_VI,
    chip,
    format_year,
    year_range,
)


def _esc(text: str | None) -> str:
    return html.escape(text or "")


def is_favorite(entity_id: str) -> bool:
    return entity_id in st.session_state.setdefault("favorites", {})


def toggle_favorite(entity_id: str, name: str, entity_type: str) -> None:
    favs = st.session_state.setdefault("favorites", {})
    if entity_id in favs:
        del favs[entity_id]
    else:
        favs[entity_id] = {"name": name, "type": entity_type}


def ask_about(question: str) -> None:
    st.session_state["pending_q"] = question
    st.switch_page(st.session_state["_pages"]["chat"])


def key_facts(subgraph: dict) -> dict[str, list]:
    nodes = subgraph.get("nodes") or []
    facts: dict[str, list] = {"times": [], "places": [], "people": [], "events": []}
    for n in nodes:
        label = n.get("display_name") or n.get("name") or ""
        kind = n.get("type")
        if kind == "Event":
            facts["events"].append(label)
            if n.get("start_year") is not None:
                facts["times"].append((n["start_year"], label))
        elif kind == "Place":
            facts["places"].append(label)
        elif kind == "Person":
            facts["people"].append(label)
    facts["times"] = sorted(set(facts["times"]))
    for key in ("places", "people", "events"):
        facts[key] = list(dict.fromkeys(facts[key]))
    return facts


def render_key_facts(subgraph: dict) -> None:
    facts = key_facts(subgraph)
    if not any(facts.values()):
        return
    cols = st.columns(4)
    blocks = [
        ("📅 Thời gian", [format_year(y) for y, _ in facts["times"]]),
        ("📍 Địa điểm", facts["places"]),
        ("👤 Nhân vật liên quan", facts["people"]),
        ("⚔️ Sự kiện", facts["events"]),
    ]
    for col, (title, items) in zip(cols, blocks):
        with col:
            st.markdown(f"**{title}**")
            if items:
                for item in items[:6]:
                    st.markdown(f"<span class='vs-muted'>• {_esc(item)}</span>", unsafe_allow_html=True)
            else:
                st.markdown("<span class='vs-muted'>Chưa có dữ liệu</span>", unsafe_allow_html=True)


def render_sources(citations: list[dict]) -> None:
    if not citations:
        return
    with st.expander(f"📚 Nguồn ({len(citations)})"):
        for c in citations:
            st.markdown(f"**[{c['n']}] {c['title']}** · {c['section']}")
            st.markdown(f"> {c['quote']}")
            st.markdown(f"[Đọc bài gốc trên Wikipedia]({c['url']})")
            st.divider()


def render_graph(subgraph: dict, height: int = 460) -> None:
    nodes = subgraph.get("nodes") or []
    edges = subgraph.get("edges") or []
    if not nodes:
        st.caption("Chưa có sơ đồ quan hệ cho nội dung này.")
        return
    node_ids = {n["id"] for n in nodes}
    ag_nodes = [
        Node(
            id=n["id"],
            label=n.get("display_name") or n.get("name") or n["id"],
            title=TYPE_VI.get(n.get("type"), TYPE_VI["Entity"]),
            color=TYPE_COLOR.get(n.get("type"), TYPE_COLOR["Entity"]),
            size=16 + min(int(n.get("degree") or 0), 20),
        )
        for n in nodes
    ]
    ag_edges = [
        Edge(source=e["source_id"], target=e["target_id"], label=RELATION_VI.get(e.get("type"), ""))
        for e in edges
        if e["source_id"] in node_ids and e["target_id"] in node_ids
    ]
    agraph(nodes=ag_nodes, edges=ag_edges, config=Config(height=height, width=760, directed=True, physics=True))
    legend = "  ·  ".join(
        f"<span style='color:{TYPE_COLOR[t]}'>●</span> {TYPE_VI[t]}" for t in TYPE_VI if t != "Entity"
    )
    st.markdown(f"<span class='vs-muted'>{legend}</span>", unsafe_allow_html=True)


def context_panel(subgraph: dict, key_prefix: str) -> None:
    """Khung ngữ cảnh bên phải: chi tiết sự kiện nổi bật nhất trong câu trả lời."""
    nodes = subgraph.get("nodes") or []
    edges = subgraph.get("edges") or []
    by_id = {n["id"]: n for n in nodes}
    events = [n for n in nodes if n.get("type") == "Event"]
    if not events:
        st.caption("Chọn một câu trả lời có sự kiện để xem chi tiết tại đây.")
        return
    event = max(events, key=lambda n: (n.get("start_year") is not None, n.get("degree") or 0))
    name = event.get("display_name") or event.get("name")

    leaders = [by_id[e["source_id"]] for e in edges
               if e["target_id"] == event["id"] and e.get("type") == "PARTICIPATED_IN"
               and e["source_id"] in by_id and by_id[e["source_id"]].get("type") == "Person"]
    places = [by_id[e["target_id"]] for e in edges
              if e["source_id"] == event["id"] and e.get("type") == "OCCURRED_AT"
              and e["target_id"] in by_id]
    related_people = [n for n in nodes if n.get("type") == "Person" and n["id"] != event["id"]]
    related_events = [n for n in events if n["id"] != event["id"]]

    with st.container(border=True):
        st.markdown(f"#### {name}")
        st.markdown(f"**Thời gian:** {year_range(event.get('start_year'), event.get('end_year'))}")
        if leaders:
            st.markdown(f"**Người chỉ huy:** {leaders[0].get('display_name') or leaders[0].get('name')}")
        if places:
            st.markdown(f"**Địa điểm:** {places[0].get('display_name') or places[0].get('name')}")
        if related_people:
            st.markdown("**Nhân vật liên quan:** " + ", ".join(
                (n.get("display_name") or n.get("name")) for n in related_people[:5]))
        if related_events:
            st.markdown("**Sự kiện liên quan:**")
            for n in related_events[:5]:
                st.markdown(f"- {n.get('display_name') or n.get('name')}")
        if st.button("🕰️ Xem trên dòng thời gian", key=f"{key_prefix}_tl", use_container_width=True):
            st.session_state["timeline_focus"] = event.get("id")
            st.switch_page(st.session_state["_pages"]["timeline"])


def render_answer(message: dict, key_prefix: str) -> None:
    subgraph = message.get("subgraph") or {}
    meaning = (message.get("significance") or "").strip()
    if meaning:
        with st.container(border=True):
            st.markdown(f"**💡 Ý nghĩa lịch sử**\n\n{_esc(meaning)}")
    render_key_facts(subgraph)
    render_sources(message.get("citations") or [])
    if subgraph.get("nodes"):
        with st.expander("🕸️ Mạng lưới lịch sử"):
            render_graph(subgraph)


def entity_card(item: dict, key: str, show_favorite: bool = True) -> None:
    kind = item.get("type") or "Entity"
    name = item.get("name") or item.get("id")
    years = year_range(item.get("start_year"), item.get("end_year"))
    st.markdown(
        f"<div class='vs-card'>"
        f"<div class='vs-muted'>{TYPE_ICON.get(kind, '•')} {TYPE_VI.get(kind, 'Khác')}</div>"
        f"<h4>{_esc(name)}</h4>"
        f"<div class='vs-muted'>{years}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([3, 2])
    if c1.button("Xem chi tiết", key=f"{key}_open", use_container_width=True):
        show_entity(item["id"])
    if show_favorite:
        starred = is_favorite(item["id"])
        if c2.button("★" if starred else "☆", key=f"{key}_fav", help="Yêu thích",
                     use_container_width=True):
            toggle_favorite(item["id"], name, kind)
            st.rerun()


def _period_names() -> dict[str, str]:
    try:
        return {p["id"]: p["name"] for era in periods_tree() for p in era["periods"]}
    except ApiUnavailable:
        return {}


@st.dialog("Chi tiết", width="large")
def show_entity(entity_id: str) -> None:
    try:
        data = entity_detail(entity_id)
    except ApiUnavailable:
        st.error("Chưa tải được thông tin lúc này.")
        return
    ent = data.get("entity") or {}
    name = ent.get("display_name") or ent.get("name") or entity_id
    kind = ent.get("type") or "Entity"
    st.markdown(f"### {TYPE_ICON.get(kind, '•')} {name}")
    st.markdown(f"<span class='vs-chip'>{TYPE_VI.get(kind, 'Khác')}</span>"
                f"<span class='vs-chip red'>{year_range(ent.get('start_year'), ent.get('end_year'))}</span>",
                unsafe_allow_html=True)
    if ent.get("legendary"):
        st.caption("Thông tin gắn với truyền thuyết, mốc năm có thể chưa chắc chắn.")
    if ent.get("disputed"):
        st.caption("Mốc năm này còn tranh luận giữa các sử gia.")

    period_names = _period_names()
    period_ids = ent.get("period_ids") or []
    if period_ids:
        st.markdown("**Thuộc các giai đoạn:** " + " ".join(
            chip(period_names.get(pid, pid)) for pid in period_ids), unsafe_allow_html=True)

    neighbours = [n for n in data.get("neighbours", []) if n.get("id")]
    if neighbours:
        st.markdown("**Mối quan hệ**")
        grouped: dict[str, list[str]] = {}
        for n in neighbours:
            grouped.setdefault(n.get("rel") or "", []).append(n.get("name") or n["id"])
        for rel, names in grouped.items():
            label = RELATION_VI.get(rel, "liên quan đến")
            st.markdown(f"- *{label}:* " + ", ".join(dict.fromkeys(names)))

    passages = entity_passages(entity_id)
    if passages:
        st.markdown(f"**Đoạn văn gốc nhắc đến ({len(passages)})**")
        for p in passages:
            title = f"{p.get('title') or 'Bài viết'} · {p.get('section') or ''}".strip(" ·")
            with st.expander(title):
                st.markdown(f"> {p.get('text') or ''}")
                if p.get("title"):
                    st.caption(f"Nguồn: Wikipedia tiếng Việt, bài «{p['title']}»")

    cols = st.columns(2)
    starred = is_favorite(entity_id)
    if cols[0].button("★ Bỏ yêu thích" if starred else "☆ Thêm vào yêu thích", use_container_width=True):
        toggle_favorite(entity_id, name, kind)
        st.rerun()
    if cols[1].button(f"💬 Hỏi về {name}", use_container_width=True, type="primary"):
        ask_about(f"{name} là ai và có vai trò gì trong lịch sử Việt Nam?")

    if neighbours:
        st.markdown("**Mạng lưới quan hệ**")
        nodes = [{"id": entity_id, "display_name": name, "type": kind, "degree": 10}]
        edges = []
        for n in neighbours[:20]:
            nodes.append({"id": n["id"], "display_name": n.get("name"), "type": n.get("type"), "degree": 2})
            edges.append({"source_id": entity_id, "target_id": n["id"], "type": n.get("rel")})
        render_graph({"nodes": nodes, "edges": edges}, height=380)
