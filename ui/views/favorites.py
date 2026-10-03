"""Trang Yêu thích: các nhân vật, sự kiện, triều đại đã đánh dấu trong phiên làm việc này."""
from __future__ import annotations

import streamlit as st
from components import toggle_favorite
from theme import TYPE_ICON, TYPE_VI


def render() -> None:
    st.markdown("## Yêu thích")
    st.markdown("<span class='vs-muted'>Những mục bạn đã đánh dấu ★. Danh sách được lưu trong phiên làm việc hiện tại.</span>",
                unsafe_allow_html=True)
    favs = st.session_state.get("favorites", {})
    if not favs:
        st.info("Bạn chưa đánh dấu mục nào. Hãy bấm ☆ ở trang Nhân vật, Sự kiện hoặc Triều đại.")
        return
    for entity_id, info in list(favs.items()):
        kind = info.get("type") or "Entity"
        c1, c2 = st.columns([6, 1])
        with c1:
            st.markdown(f"**{TYPE_ICON.get(kind, '•')} {info['name']}** · *{TYPE_VI.get(kind, 'Khác')}*")
        with c2:
            if st.button("Bỏ", key=f"unfav_{entity_id}", use_container_width=True):
                toggle_favorite(entity_id, info["name"], kind)
                st.rerun()
