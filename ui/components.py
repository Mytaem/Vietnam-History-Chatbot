"""Thành phần UI: vẽ subgraph (streamlit-agraph), timeline theo màu era, thẻ nguồn. (M7)"""
from __future__ import annotations

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

TYPE_COLOR = {
    "Person": "#2f5d8a", "Event": "#b5452f", "Place": "#5b8e7d", "Polity": "#c9a227",
    "Organization": "#8c6d46", "Work": "#7e57c2", "Culture": "#9e9e9e", "Entity": "#607d8b",
}


def render_graph(subgraph: dict, key: str = "graph") -> None:
    nodes = subgraph.get("nodes") or []
    edges = subgraph.get("edges") or []
    if not nodes:
        st.info("Chưa có đồ thị cho câu hỏi này.")
        return
    node_ids = {n["id"] for n in nodes}
    ag_nodes = [
        Node(
            id=n["id"],
            label=n.get("display_name") or n.get("name") or n["id"],
            color=TYPE_COLOR.get(n.get("type"), TYPE_COLOR["Entity"]),
            size=16 + min(int(n.get("degree") or 0), 20),
        )
        for n in nodes
    ]
    ag_edges = [
        Edge(source=e["source_id"], target=e["target_id"], label=e.get("type", ""))
        for e in edges
        if e["source_id"] in node_ids and e["target_id"] in node_ids
    ]
    config = Config(height=520, width=800, directed=True, physics=True, hierarchical=False)
    clicked = agraph(nodes=ag_nodes, edges=ag_edges, config=config)
    if clicked:
        st.session_state["graph_clicked_entity"] = clicked
    legend = " · ".join(f"<span style='color:{c}'>●</span> {t}" for t, c in TYPE_COLOR.items() if t != "Entity")
    st.markdown(legend, unsafe_allow_html=True)


def _fmt_year(y: int) -> str:
    return f"{-y} TCN" if y < 0 else str(y)


def render_timeline(events: list[dict], eras: list[dict] | None = None) -> None:
    """Dòng thời gian dạng danh sách mốc năm tăng dần (không phụ thuộc thư viện vẽ ngoài)."""
    if not events:
        st.info("Không có mốc năm nào để vẽ dòng thời gian.")
        return
    for ev in sorted(events, key=lambda e: e["year"]):
        st.markdown(f"— **{_fmt_year(ev['year'])}** &nbsp; {ev['label']}")


def render_sources(citations: list[dict]) -> None:
    if not citations:
        st.info("Không có nguồn trích dẫn.")
        return
    for c in citations:
        with st.container(border=True):
            st.markdown(f"**[{c['n']}] {c['title']} › {c['section']}**")
            st.caption(c["quote"])
            st.markdown(f"[Xem trên Wikipedia]({c['url']})")
