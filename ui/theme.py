"""Màu sắc, CSS và các hàm hiển thị dùng chung cho toàn bộ giao diện Việt Sử AI."""
from __future__ import annotations

import streamlit as st

RED = "#7A1C1C"
NAVY = "#1F2A3C"
BEIGE = "#F3E9D2"
PAPER = "#FBF6EA"
GOLD = "#B8912A"
BRONZE = "#6B4A2B"
MUTED = "#6B5E4B"

TYPE_VI = {
    "Person": "Nhân vật",
    "Event": "Sự kiện",
    "Place": "Địa danh",
    "Polity": "Triều đại",
    "Organization": "Tổ chức",
    "Work": "Tác phẩm",
    "Culture": "Văn hóa",
    "Entity": "Khác",
}

TYPE_ICON = {
    "Person": "👤",
    "Event": "⚔️",
    "Place": "📍",
    "Polity": "👑",
    "Organization": "🏛️",
    "Work": "📜",
    "Culture": "🏺",
    "Entity": "•",
}

ERA_ICON = {
    "tiensu": "🦴",
    "dungnuoc": "🏺",
    "bacthuoc": "⚔️",
    "songsong": "🏯",
    "phongkien": "👑",
    "candai": "🇻🇳",
}

RELATION_VI = {
    "CHILD_OF": "là con của",
    "SPOUSE_OF": "là vợ/chồng của",
    "SUCCEEDED": "kế vị",
    "PARTICIPATED_IN": "tham gia",
    "OCCURRED_AT": "diễn ra tại",
    "CAPITAL_OF": "là kinh đô của",
    "FOUNDED": "lập ra",
    "RULED": "cai trị",
    "BORN_IN": "sinh tại",
    "DIED_IN": "mất tại",
    "AUTHORED": "là tác giả của",
    "OPPOSED": "đối địch với",
    "COMMANDED": "chỉ huy",
    "LOCATED_IN": "nằm ở",
}

TYPE_COLOR = {
    "Person": "#2F4F6F", "Event": "#7A1C1C", "Place": "#4D6B4F", "Polity": "#B8912A",
    "Organization": "#6B4A2B", "Work": "#5E4378", "Culture": "#7D7D7D", "Entity": "#5E6B73",
}

# Họa tiết trống đồng Đông Sơn: vòng tròn đồng tâm và tia mặt trời, rất nhạt, chỉ làm nền.
_PATTERN = (
    "url(\"data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'>"
    "<g fill='none' stroke='%236B4A2B' stroke-opacity='0.07' stroke-width='1.2'>"
    "<circle cx='110' cy='110' r='24'/><circle cx='110' cy='110' r='48'/>"
    "<circle cx='110' cy='110' r='72'/><circle cx='110' cy='110' r='96'/>"
    "<path d='M110 14v192M14 110h192M42 42l136 136M178 42L42 178'/></g>"
    "<g fill='%236B4A2B' fill-opacity='0.06'><circle cx='110' cy='110' r='6'/></g></svg>\")"
)

_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif:wght@400;600;700&family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp {{ font-family: 'Be Vietnam Pro', 'Segoe UI', sans-serif; }}
.stApp {{
    background-color: {BEIGE};
    background-image: radial-gradient(ellipse at top, rgba(251,246,234,0.85), rgba(243,233,210,0) 70%), {_PATTERN};
}}
h1, h2, h3, h4 {{ color: {NAVY}; font-family: 'Noto Serif', 'Times New Roman', serif; letter-spacing: 0; }}
h2 {{ position: relative; padding-bottom: .45rem; }}
h2::after {{
    content: ""; display: block; width: 88px; height: 3px; margin-top: .4rem;
    background: linear-gradient(90deg, {RED}, {GOLD}); border-radius: 2px;
}}
hr, [data-testid="stDivider"] {{ border: none !important; height: 1px !important;
    background: repeating-linear-gradient(90deg, {GOLD} 0 6px, transparent 6px 12px) !important; }}
[data-testid="stSidebar"] {{ background: linear-gradient(180deg, {NAVY}, #2A2A33); border-right: 2px solid {GOLD}; }}
[data-testid="stSidebar"] * {{ color: #F3E9D2; }}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: #E7C873; font-family: 'Noto Serif', serif; }}
[data-testid="stSidebar"] h2::after {{ display: none; }}
[data-testid="stSidebar"] .vs-muted {{ color: #CFC3A6 !important; }}
[data-testid="stSidebar"] hr {{ background: repeating-linear-gradient(90deg, {GOLD} 0 6px, transparent 6px 12px) !important; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {{ border-radius: 4px; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(184,145,42,0.22); border-left: 3px solid {GOLD};
}}
.block-container {{ padding-top: 1.6rem; max-width: 1100px; }}
[data-testid="stChatMessage"] {{
    background: {PAPER}; border: 1px solid rgba(107,74,43,0.25); border-radius: 6px;
    box-shadow: 0 1px 0 rgba(107,74,43,0.12);
}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
    background: #F1E2C4;
}}
.vs-card {{
    background: {PAPER}; border-radius: 4px; padding: 1rem 1.1rem; position: relative;
    border: 1px solid {GOLD};
    box-shadow: inset 0 0 0 3px {PAPER}, inset 0 0 0 4px rgba(184,145,42,0.45);
    transition: transform .15s ease, box-shadow .15s ease; height: 100%;
}}
.vs-card:hover {{ transform: translateY(-2px); box-shadow: inset 0 0 0 3px {PAPER}, inset 0 0 0 4px rgba(184,145,42,0.7), 0 6px 14px rgba(107,74,43,0.15); }}
.vs-card h4 {{ margin: .35rem 0 .2rem 0; color: {NAVY}; font-size: 1.05rem; }}
.vs-muted {{ color: {MUTED}; font-size: .88rem; }}
.vs-chip {{
    display: inline-block; padding: 2px 10px; border-radius: 2px; font-size: .78rem;
    background: rgba(184,145,42,0.18); color: {BRONZE}; margin-right: 6px; border: 1px solid {GOLD};
    font-family: 'Noto Serif', serif;
}}
.vs-chip.red {{ background: rgba(122,28,28,0.10); color: {RED}; border-color: rgba(122,28,28,0.45); }}
.vs-hero {{
    background: linear-gradient(160deg, {NAVY} 0%, #34303A 55%, {RED} 150%);
    color: #F3E9D2; border-radius: 4px; padding: 2.4rem 2.2rem; position: relative; overflow: hidden;
    border: 1px solid {GOLD};
    box-shadow: inset 0 0 0 6px {NAVY}, inset 0 0 0 7px rgba(184,145,42,0.6);
}}
.vs-hero::before {{
    content: "❖"; position: absolute; right: 1.6rem; top: .8rem; color: rgba(231,200,115,0.45); font-size: 2.2rem;
}}
.vs-hero h1 {{ color: #F3E9D2; font-size: 2.2rem; margin: 0 0 .6rem 0; font-family: 'Noto Serif', serif; line-height: 1.25; }}
.vs-hero p {{ color: #E7DCC0; margin: 0; font-size: 1.02rem; }}
.vs-seal {{
    display: inline-block; width: 26px; height: 26px; line-height: 26px; text-align: center;
    background: {RED}; color: {PAPER}; border-radius: 3px; font-family: 'Noto Serif', serif; font-weight: 700; margin-right: 8px;
}}
.vs-tl-dot {{ width: 12px; height: 12px; background: {RED}; transform: rotate(45deg); margin-top: 20px; flex: 0 0 12px; }}
.vs-status {{ color: {MUTED}; font-size: .9rem; }}
button[kind="secondary"] {{ border-color: {GOLD} !important; color: {BRONZE} !important; font-family: 'Noto Serif', serif; }}
button[kind="primary"] {{ background: {RED} !important; border-color: {RED} !important; font-family: 'Noto Serif', serif; }}
[data-testid="stExpander"] {{ border: 1px solid rgba(184,145,42,0.5); border-radius: 4px; background: rgba(251,246,234,0.6); }}
"""


def inject_css() -> None:
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def format_year(y: int | None) -> str:
    if y is None:
        return "không rõ năm"
    return f"năm {-y} TCN" if y < 0 else f"năm {y}"


def year_range(start: int | None, end: int | None) -> str:
    if start is None and end is None:
        return "Không rõ thời gian"
    if end is None or end == start:
        return format_year(start)
    if start is None:
        return f"đến {format_year(end)}"
    return f"{format_year(start)} – {format_year(end)}"


def chip(text: str, red: bool = False) -> str:
    cls = "vs-chip red" if red else "vs-chip"
    return f"<span class='{cls}'>{text}</span>"
