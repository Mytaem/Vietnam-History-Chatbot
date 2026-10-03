"""Các trang duyệt danh mục: nhân vật, sự kiện, triều đại, địa danh (tìm kiếm, lọc giai đoạn, sắp xếp)."""
from __future__ import annotations

import streamlit as st
from api import ApiUnavailable, list_entities, periods_tree
from components import entity_card
from theme import TYPE_VI

COLS = 3
SORTS = {
    "Được nhắc đến nhiều nhất": None,
    "Theo năm (cũ → mới)": "year",
    "Theo tên (A → Z)": "name",
}


def _period_options() -> dict[str, str | None]:
    options: dict[str, str | None] = {"Tất cả giai đoạn": None}
    try:
        for era in periods_tree():
            for p in era["periods"]:
                options[f"{era['name']} — {p['name']}"] = p["id"]
    except ApiUnavailable:
        pass
    return options


def render_browse(title: str, subtitle: str, entity_type: str, key: str, note: str | None = None) -> None:
    st.markdown(f"## {title}")
    st.markdown(f"<span class='vs-muted'>{subtitle}</span>", unsafe_allow_html=True)
    if note:
        st.info(note)

    c1, c2, c3 = st.columns([3, 2.5, 2])
    query = c1.text_input("Tìm kiếm", key=f"{key}_q", placeholder="Nhập tên để tìm...")
    periods = _period_options()
    period_label = c2.selectbox("Giai đoạn", list(periods), key=f"{key}_period")
    sort_label = c3.selectbox("Sắp xếp", list(SORTS), key=f"{key}_sort")

    try:
        items = list_entities(entity_type, query.strip() or None, limit=120, period=periods[period_label])
    except ApiUnavailable:
        st.error("Chưa tải được danh sách lúc này. Vui lòng thử lại sau.")
        return

    sort_key = SORTS[sort_label]
    if sort_key == "year":
        items = sorted(items, key=lambda i: (i.get("start_year") is None, i.get("start_year") or 0))
    elif sort_key == "name":
        items = sorted(items, key=lambda i: (i.get("name") or "").casefold())

    if not items:
        st.caption("Không có mục nào khớp với tìm kiếm và bộ lọc hiện tại.")
        return

    dated = sum(1 for i in items if i.get("start_year") is not None)
    st.caption(
        f"{len(items)} {TYPE_VI.get(entity_type, 'mục').lower()} · {dated} có mốc năm rõ ràng · "
        "bấm Chi tiết để xem đoạn văn gốc, quan hệ và giai đoạn."
    )
    for row_start in range(0, len(items), COLS):
        cols = st.columns(COLS)
        for col, item in zip(cols, items[row_start:row_start + COLS]):
            with col:
                entity_card(item, key=f"{key}_{item['id']}")
