"""Trang chủ: giới thiệu, lối vào nhanh các chủ đề và trạng thái hệ thống."""
from __future__ import annotations

import streamlit as st
from api import health
from components import ask_about

TOPICS = [
    ("👑", "Các triều đại", "Từ nhà Đinh đến nhà Nguyễn", "pages/dynasties"),
    ("👤", "Nhân vật lịch sử", "Những con người làm nên lịch sử", "pages/people"),
    ("⚔️", "Các cuộc kháng chiến", "Chống ngoại xâm qua các thời đại", "pages/events"),
    ("🏺", "Văn hóa Việt Nam", "Văn hóa Đông Sơn, Sa Huỳnh, Óc Eo", "chat"),
    ("🕰️", "Dòng thời gian", "Xem toàn bộ tiến trình lịch sử", "pages/timeline"),
    ("🇻🇳", "Sự kiện năm 1945", "Cách mạng tháng Tám và Tuyên ngôn độc lập", "chat"),
]


def render(pages: dict) -> None:
    st.markdown(
        """
        <div class='vs-hero'>
          <h1>Khám phá lịch sử Việt Nam<br>từ tiền sử đến 1945</h1>
          <p>Hỏi – khám phá – kết nối các sự kiện, nhân vật và triều đại qua một trợ lý AI lịch sử.</p>
          <div style='margin-top:14px;display:flex;gap:10px;flex-wrap:wrap'>
            <span class='vs-chip' style='background:rgba(247,241,227,.15);color:#F7F1E3;border-color:rgba(247,241,227,.3)'>🏺 Tiền sử</span>
            <span class='vs-chip' style='background:rgba(247,241,227,.15);color:#F7F1E3;border-color:rgba(247,241,227,.3)'>⚔️ Chống ngoại xâm</span>
            <span class='vs-chip' style='background:rgba(247,241,227,.15);color:#F7F1E3;border-color:rgba(247,241,227,.3)'>👑 Các triều đại</span>
            <span class='vs-chip' style='background:rgba(247,241,227,.15);color:#F7F1E3;border-color:rgba(247,241,227,.3)'>🇻🇳 1945</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    c1, c2 = st.columns(2)
    if c1.button("💬 Bắt đầu trò chuyện", type="primary", use_container_width=True):
        st.switch_page(pages["chat"])
    if c2.button("🕰️ Khám phá dòng thời gian", use_container_width=True):
        st.switch_page(pages["timeline"])

    st.markdown("### Bạn muốn khám phá điều gì?")
    cols = st.columns(3)
    for i, (icon, title, desc, target) in enumerate(TOPICS):
        with cols[i % 3]:
            st.markdown(
                f"<div class='vs-card'><div style='font-size:1.6rem'>{icon}</div>"
                f"<h4>{title}</h4><div class='vs-muted'>{desc}</div></div>",
                unsafe_allow_html=True,
            )
            if st.button("Khám phá", key=f"topic_{i}", use_container_width=True):
                if target == "chat":
                    ask_about(title + " — hãy tóm tắt cho tôi.")
                else:
                    st.switch_page(pages[target.split("/")[-1]])

    status = health()
    if status.get("status") == "ok":
        st.caption("● Hệ thống đang hoạt động")
    else:
        st.caption("● Hệ thống đang bảo trì, một số tính năng có thể tạm thời không khả dụng")
