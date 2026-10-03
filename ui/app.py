"""Việt Sử AI — điểm vào của ứng dụng Streamlit (chạy: streamlit run ui/app.py)."""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Việt Sử AI — Chatbot Lịch sử Việt Nam", page_icon="🇻🇳", layout="wide")

from theme import inject_css  # noqa: E402
from views import browse, chat, favorites, home, timeline  # noqa: E402
from views import map as map_page  # noqa: E402

inject_css()
chat.init_state()

st.sidebar.markdown("## 🇻🇳 Việt Sử AI")

pages = {
    "home": st.Page(lambda: home.render(st.session_state["_pages"]), title="Trang chủ", icon="🏠", default=True),
    "chat": st.Page(chat.render, title="Chat lịch sử", icon="💬", url_path="chat"),
    "timeline": st.Page(timeline.render, title="Dòng thời gian", icon="🕰️", url_path="timeline"),
    "dynasties": st.Page(
        lambda: browse.render_browse(
            "Các triều đại",
            "Những vương triều đã cai trị Việt Nam, từ nhà Đinh đến nhà Nguyễn.",
            "Polity", key="dyn",
        ),
        title="Các triều đại", icon="👑", url_path="dynasties",
    ),
    "people": st.Page(
        lambda: browse.render_browse(
            "Nhân vật lịch sử",
            "Những con người làm nên lịch sử Việt Nam.",
            "Person", key="ppl",
        ),
        title="Nhân vật lịch sử", icon="👤", url_path="people",
    ),
    "events": st.Page(
        lambda: browse.render_browse(
            "Sự kiện quan trọng",
            "Các trận đánh, cuộc khởi nghĩa và biến cố tiêu biểu.",
            "Event", key="evt",
        ),
        title="Sự kiện quan trọng", icon="⚔️", url_path="events",
    ),
    "map": st.Page(map_page.render, title="Bản đồ lịch sử", icon="🗺️", url_path="map"),
    "favorites": st.Page(favorites.render, title="Yêu thích", icon="⭐", url_path="favorites"),
}
st.session_state["_pages"] = pages

nav = st.navigation(list(pages.values()), position="sidebar")

with st.sidebar:
    st.divider()
    chat.sidebar_recent()

nav.run()
