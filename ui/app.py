"""Streamlit UI: Chat | Đồ thị | Timeline | Nguồn | Khám phá giai đoạn | Debug (PLAN.md 6.5). (M7)"""
from __future__ import annotations

import json
import os

import httpx
import streamlit as st
from components import render_graph, render_sources, render_timeline

API_URL = os.environ.get("API_URL", "http://localhost:8000")
SAMPLE_QUESTIONS = [
    "Văn hóa Hòa Bình và văn hóa Bắc Sơn khác nhau thế nào?",
    "An Dương Vương xây thành Cổ Loa ở đâu và vì sao Âu Lạc mất nước?",
    "Kể tên các cuộc khởi nghĩa thời Bắc thuộc theo thứ tự thời gian.",
    "Ba trận Bạch Đằng (938, 981, 1288) khác nhau thế nào về người chỉ huy và đối thủ?",
    "Vị vua nào trị vì khi diễn ra trận Bạch Đằng năm 1288, và cha của vị vua đó là ai?",
    "Quang Trung và Gia Long có quan hệ gì?",
    "Tóm tắt thời kỳ Trịnh – Nguyễn phân tranh.",
    "Chiến dịch Điện Biên Phủ diễn ra thế nào?",
]

st.set_page_config(page_title="Chatbot Lịch sử Việt Nam", page_icon="📜", layout="wide")


@st.cache_data(ttl=10)
def _health() -> dict:
    try:
        return httpx.get(f"{API_URL}/health", timeout=5).json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


@st.cache_data(ttl=60)
def _periods_tree() -> dict:
    try:
        return httpx.get(f"{API_URL}/periods", timeout=10).json()
    except Exception:
        return {"eras": []}


def _period_detail(period_id: str) -> dict:
    try:
        return httpx.get(f"{API_URL}/periods/{period_id}", timeout=10).json()
    except Exception as e:
        return {"error": str(e)}


def _stream_chat(question: str, history: list[dict], period_filter, mode: str):
    """Trả về (iterator token để hiển thị dần, hàm lấy kết quả 'done' sau khi stream xong)."""
    payload = {"question": question, "history": history, "mode": mode}
    if period_filter:
        payload["period_filter"] = list(period_filter)
    done: dict = {}

    def gen():
        with httpx.stream("POST", f"{API_URL}/chat", json=payload, timeout=120) as resp:
            event, data_lines = None, []
            for raw_line in resp.iter_lines():
                line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8")
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
                elif line == "":
                    data = "\n".join(data_lines)
                    data_lines = []
                    if event == "token":
                        yield data
                    elif event == "plan":
                        st.session_state["last_plan"] = json.loads(data) if data else {}
                    elif event == "done":
                        done.update(json.loads(data))
                    event = None

    return gen(), done


if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None

with st.sidebar:
    st.header("Trạng thái")
    health = _health()
    if health.get("status") == "ok":
        st.success("API + Neo4j + Ollama đều OK")
    else:
        st.error(f"Hệ thống chưa sẵn sàng: {health}")
    st.caption(f"API: {API_URL}")

    st.header("Tùy chọn truy hồi")
    mode = "graphrag" if st.toggle("Dùng GraphRAG (tắt = chỉ vector)", value=True) else "vector"
    tree = _periods_tree()
    period_options = {"(không lọc)": None}
    for era in tree.get("eras", []):
        for p in era["periods"]:
            period_options[f"{era['name']} › {p['name']}"] = (p["start"], p["end"])
    period_label = st.selectbox("Giới hạn theo giai đoạn", list(period_options))
    period_filter = period_options[period_label]

    st.header("Câu hỏi mẫu")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True, key=f"sample_{hash(q)}"):
            st.session_state["pending_question"] = q

st.title("📜 Chatbot Lịch sử Việt Nam (tiền sử → 1945)")

col_chat, col_tabs = st.columns([3, 2])

with col_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("Hỏi về lịch sử Việt Nam…") or st.session_state.pop("pending_question", None)
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
        with st.chat_message("assistant"):
            token_gen, done_box = _stream_chat(question, history, period_filter, mode)
            full_text = st.write_stream(token_gen)
        answer_text = done_box.get("answer", full_text)
        st.session_state.messages.append({"role": "assistant", "content": answer_text})
        st.session_state.last_result = done_box
        st.rerun()

with col_tabs:
    tabs = st.tabs(["Đồ thị", "Timeline", "Nguồn", "Khám phá giai đoạn", "Debug"])
    result = st.session_state.last_result or {}

    with tabs[0]:
        render_graph(result.get("subgraph", {}))

    with tabs[1]:
        render_timeline(result.get("timeline", []))

    with tabs[2]:
        render_sources(result.get("citations", []))

    with tabs[3]:
        era_names = [e["name"] for e in tree.get("eras", [])]
        if era_names:
            era_pick = st.selectbox("Thời kỳ", era_names, key="explore_era")
            era = next(e for e in tree["eras"] if e["name"] == era_pick)
            period_pick = st.selectbox("Giai đoạn", [p["name"] for p in era["periods"]], key="explore_period")
            period = next(p for p in era["periods"] if p["name"] == period_pick)
            detail = _period_detail(period["id"])
            st.write(f"**{detail.get('name')}** ({detail.get('start')} – {detail.get('end')})")
            if detail.get("legendary"):
                st.caption("Giai đoạn mang tính truyền thuyết.")
            for ent in detail.get("top_entities", []):
                st.markdown(f"- **{ent['name']}** ({ent.get('type', 'Entity')})")
            cols = st.columns(3)
            cols[0].text_input("Câu hỏi gợi ý 1", f"Tóm tắt {period['name']}.", disabled=True)
            cols[1].text_input("Câu hỏi gợi ý 2", f"Nhân vật tiêu biểu của {period['name']} là ai?", disabled=True)
            cols[2].text_input("Câu hỏi gợi ý 3", f"{period['name']} diễn ra những sự kiện gì?", disabled=True)
        else:
            st.info("Chưa tải được danh sách giai đoạn từ API.")

    with tabs[4]:
        st.subheader("QueryPlan")
        st.json(st.session_state.get("last_plan", {}))
        st.subheader("Kết quả truy hồi (rút gọn)")
        st.json({
            "out_of_scope": result.get("out_of_scope"),
            "so_chunk": len(result.get("citations", [])),
            "so_node": len(result.get("subgraph", {}).get("nodes", [])),
            "so_canh": len(result.get("subgraph", {}).get("edges", [])),
        })
