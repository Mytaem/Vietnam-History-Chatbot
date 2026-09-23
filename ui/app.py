"""Streamlit UI: Chat | Đồ thị | Timeline | Nguồn | Khám phá giai đoạn | Debug (PLAN.md 6.5). (M7)"""
import streamlit as st

st.set_page_config(page_title="Chatbot Lịch sử Việt Nam", page_icon="📜", layout="wide")
st.title("Chatbot Lịch sử Việt Nam (tiền sử → 1945)")
st.info("Khung giao diện - sẽ triển khai ở M7.")

# TODO(M7): sidebar (/health, lọc giai đoạn, GraphRAG ↔ vector, rerank, câu hỏi mẫu)
# TODO(M7): cột chat (stream SSE từ /chat) + tabs Đồ thị / Timeline / Nguồn / Khám phá giai đoạn / Debug
