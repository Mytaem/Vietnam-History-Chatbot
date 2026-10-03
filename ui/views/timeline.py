"""Dòng thời gian lịch sử Việt Nam: các thời kỳ theo trình tự, mở chi tiết giai đoạn và các mục theo năm."""
from __future__ import annotations

import streamlit as st
from api import ApiUnavailable, entity_detail, period_detail, period_items, periods_tree
from components import ask_about, show_entity
from theme import ERA_ICON, TYPE_ICON, TYPE_VI, year_range


def _open_period(period_id: str) -> None:
    st.session_state["open_period"] = period_id


def _focus_from_context() -> None:
    focus = st.session_state.pop("timeline_focus", None)
    if not focus:
        return
    try:
        ent = entity_detail(focus).get("entity") or {}
    except ApiUnavailable:
        return
    period_ids = ent.get("period_ids") or []
    if period_ids:
        st.session_state["open_period"] = period_ids[0]


def _period_panel(period_id: str) -> None:
    try:
        detail = period_detail(period_id)
        items = period_items(period_id)
    except ApiUnavailable:
        st.error("Chưa tải được thông tin giai đoạn này.")
        return

    with st.container(border=True):
        head, close = st.columns([6, 1])
        with head:
            st.markdown(f"### {detail.get('name')}")
            st.markdown(
                f"<span class='vs-chip red'>{year_range(detail.get('start'), detail.get('end'))}</span>",
                unsafe_allow_html=True,
            )
        with close:
            if st.button("Đóng", key="close_period", use_container_width=True):
                st.session_state.pop("open_period", None)
                st.rerun()

        if detail.get("legendary"):
            st.caption("Giai đoạn gắn với nhiều truyền thuyết, mốc năm có thể chưa chắc chắn.")
        if detail.get("disputed"):
            st.caption("Các mốc năm của giai đoạn này còn tranh luận giữa các sử gia.")

        events = [i for i in items if i.get("type") == "Event"]
        people = [i for i in items if i.get("type") == "Person"]
        st.markdown(f"**Sự kiện ({len(events)}) và nhân vật ({len(people)}) theo thứ tự thời gian**")
        if not items:
            st.caption("Chưa có sự kiện hoặc nhân vật nào được gắn với giai đoạn này trong dữ liệu.")
        for item in items:
            kind = item.get("type") or "Entity"
            c1, c2 = st.columns([5, 1.3])
            c1.markdown(
                f"{TYPE_ICON.get(kind, '•')} **{item.get('name')}** · {TYPE_VI.get(kind, 'Khác')} · "
                f"<span class='vs-muted'>{year_range(item.get('start_year'), item.get('end_year'))}</span>",
                unsafe_allow_html=True,
            )
            if c2.button("Chi tiết", key=f"pi_{period_id}_{item['id']}", use_container_width=True):
                show_entity(item["id"])

        if st.button(f"💬 Hỏi về {detail.get('name')}", type="primary", use_container_width=True):
            ask_about(f"Tóm tắt {detail.get('name')} và nêu các sự kiện chính.")


def render() -> None:
    st.markdown("## Dòng thời gian lịch sử Việt Nam")
    st.markdown("<span class='vs-muted'>Từ tiền sử đến năm 1945. Bấm Xem để mở chi tiết giai đoạn.</span>",
                unsafe_allow_html=True)
    try:
        eras = periods_tree()
    except ApiUnavailable:
        st.error("Chưa tải được dòng thời gian lúc này. Vui lòng thử lại sau.")
        return

    _focus_from_context()
    open_id = st.session_state.get("open_period")
    if open_id:
        _period_panel(open_id)
        st.write("")

    for era_index, era in enumerate(eras):
        icon = ERA_ICON.get(era.get("id"), "📜")
        st.markdown(f"### {icon} {era['name']}")
        for period in era["periods"]:
            c_dot, c_card = st.columns([0.04, 0.96])
            with c_dot:
                st.markdown("<div class='vs-tl-dot' style='margin-top:18px'></div>", unsafe_allow_html=True)
            with c_card:
                with st.container(border=True):
                    a, b = st.columns([4, 1.4])
                    with a:
                        st.markdown(f"**{period['name']}**")
                        st.markdown(
                            f"<span class='vs-muted'>{year_range(period.get('start'), period.get('end'))}"
                            f" · {period.get('entity_count', 0)} mục dữ liệu</span>",
                            unsafe_allow_html=True,
                        )
                    with b:
                        st.button("Xem", key=f"per_{period['id']}", use_container_width=True,
                                  on_click=_open_period, args=(period["id"],))
        if era_index < len(eras) - 1:
            st.markdown("<div style='text-align:center;color:#6B6257'>↓</div>", unsafe_allow_html=True)
