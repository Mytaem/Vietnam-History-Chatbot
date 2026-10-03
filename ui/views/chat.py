"""Trang Chat lịch sử: hỏi đáp có tiến trình, nguồn và khung ngữ cảnh."""
from __future__ import annotations

import io

import streamlit as st
from api import OFFLINE_MSG, ApiUnavailable, periods_tree, stream_chat, stream_document
from components import context_panel, render_answer

ASSISTANT_AVATAR = "🏺"

SUGGESTIONS = [
    ("🏺 Thời kỳ tiền sử", "Thời kỳ tiền sử ở Việt Nam có những nền văn hóa nào?"),
    ("🏯 Văn Lang – Âu Lạc", "Nhà nước Văn Lang – Âu Lạc hình thành như thế nào?"),
    ("⚔️ Các cuộc kháng chiến", "Chiến thắng Bạch Đằng năm 1288 diễn ra thế nào?"),
    ("👑 Các triều đại", "Tóm tắt nhà Trần."),
    ("👤 Nhân vật lịch sử", "Trần Hưng Đạo là ai?"),
    ("🇻🇳 Cách mạng tháng Tám 1945", "Cách mạng tháng Tám 1945 diễn ra thế nào?"),
]

RECENT_EXAMPLES = [
    "Nhà nước Văn Lang hình thành như thế nào?",
    "Chiến thắng Bạch Đằng năm 1288",
    "Vì sao nhà Trần thắng quân Nguyên – Mông?",
    "Phong trào Tây Sơn",
    "Cách mạng tháng Tám 1945",
]


def init_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("past_chats", [])
    st.session_state.setdefault("period_filter", None)
    st.session_state.setdefault("attached_doc", None)


def new_chat() -> None:
    msgs = st.session_state.messages
    if msgs:
        first_user = next((m["content"] for m in msgs if m["role"] == "user"), "Cuộc trò chuyện")
        st.session_state.past_chats.insert(0, {"title": first_user, "messages": msgs})
        st.session_state.past_chats = st.session_state.past_chats[:20]
    st.session_state.messages = []


def _chat_matches(chat: dict, query: str) -> bool:
    needle = query.strip().casefold()
    if needle in chat["title"].casefold():
        return True
    return any(needle in (m.get("content") or "").casefold() for m in chat["messages"])


def extract_document(upload) -> str:
    name = upload.name.lower()
    raw = upload.getvalue()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return raw.decode("utf-8", errors="ignore")


DOC_CHARS = 20000


def attach_controls() -> None:
    with st.popover("📎 Tải tài liệu", use_container_width=False):
        upload = st.file_uploader("Chọn tệp .txt, .md hoặc .pdf", type=["txt", "md", "pdf"], key="doc_upload")
        if upload is not None and st.button("Đính kèm tài liệu này", key="attach_btn", type="primary"):
            try:
                text = extract_document(upload).strip()
            except Exception:
                st.error("Không đọc được tệp này. Vui lòng thử tệp .txt, .md hoặc .pdf khác.")
                return
            if not text:
                st.error("Tệp không có nội dung văn bản.")
                return
            st.session_state.attached_doc = {"name": upload.name, "text": text[:DOC_CHARS]}
            st.rerun()
    doc = st.session_state.attached_doc
    if doc:
        st.caption(f"📎 Đang mở «{doc['name']}» ({len(doc['text']):,} ký tự). Các câu hỏi sẽ được trả lời từ nội dung tài liệu này cho tới khi bạn bỏ đính kèm.")
        if st.button("Bỏ tài liệu", key="detach_btn"):
            st.session_state.attached_doc = None
            st.rerun()


def load_chat(index: int) -> None:
    chat = st.session_state.past_chats.pop(index)
    if st.session_state.messages:
        new_chat()
    st.session_state.messages = chat["messages"]


def recent_questions() -> list[str]:
    asked = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
    for chat in st.session_state.past_chats:
        asked.append(chat["title"])
    return list(dict.fromkeys(asked))[:6] or RECENT_EXAMPLES


def _header() -> None:
    left, right = st.columns([5, 3])
    with left:
        st.markdown("## Việt Sử AI")
        st.markdown("<span class='vs-muted'>Khám phá lịch sử Việt Nam từ tiền sử đến năm 1945</span>",
                    unsafe_allow_html=True)
    with right:
        b1, b2, b3 = st.columns(3)
        if b1.button("➕ Mới", use_container_width=True, help="Cuộc trò chuyện mới"):
            new_chat()
            st.rerun()
        with b2.popover("🕘 Lịch sử", use_container_width=True):
            query = st.text_input("Tìm trong lịch sử", key="history_q", placeholder="Nhập từ khóa...")
            if not st.session_state.past_chats:
                st.caption("Chưa có cuộc trò chuyện nào được lưu.")
            for i, chat in enumerate(st.session_state.past_chats):
                if query and not _chat_matches(chat, query):
                    continue
                if st.button(chat["title"][:60], key=f"past_{i}", use_container_width=True):
                    load_chat(i)
                    st.rerun()
            if query and not any(_chat_matches(c, query) for c in st.session_state.past_chats):
                st.caption("Không tìm thấy cuộc trò chuyện nào khớp.")
        with b3.popover("⚙️ Cài đặt", use_container_width=True):
            try:
                eras = periods_tree()
            except ApiUnavailable:
                eras = []
            options: dict[str, tuple | None] = {"Tất cả thời kỳ": None}
            for era in eras:
                for p in era["periods"]:
                    options[f"{era['name']} — {p['name']}"] = (p["start"], p["end"])
            labels = list(options)
            current = next((k for k, v in options.items() if v == st.session_state.period_filter), labels[0])
            choice = st.selectbox("Giới hạn theo thời kỳ", labels, index=labels.index(current))
            st.session_state.period_filter = options[choice]


def _welcome() -> None:
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        st.markdown(
            "**Xin chào! Tôi là Việt Sử AI.**\n\n"
            "Tôi có thể giúp bạn khám phá lịch sử Việt Nam từ thời tiền sử đến năm 1945.\n\n"
            "Bạn muốn tìm hiểu về thời kỳ nào?"
        )
    cols = st.columns(3)
    for i, (label, question) in enumerate(SUGGESTIONS):
        if cols[i % 3].button(label, key=f"sugg_{i}", use_container_width=True):
            st.session_state["pending_q"] = question
            st.rerun()


def _ask(question: str) -> None:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    doc = st.session_state.attached_doc
    shown =question + (f"\n\n📎 *Tài liệu: {doc['name']}*" if doc else "")
    st.session_state.messages.append({"role": "user", "content": shown})
    with st.chat_message("user"):
        st.markdown(shown)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        status = st.status("🔎 Đang tìm kiếm tư liệu...", expanded=False)
        placeholder = st.empty()
        buffer = ""
        done: dict = {}
        try:
            if doc:
                events = stream_document(question, doc["name"], doc["text"], history)
            else:
                events = stream_chat(question, history, st.session_state.period_filter)
            for kind, payload in events:
                if kind == "token":
                    buffer += payload
                    placeholder.markdown(buffer + " ▌")
                elif kind == "done":
                    done = payload
        except ApiUnavailable:
            status.update(label="Không kết nối được hệ thống", state="error")
            st.error(OFFLINE_MSG)
            st.session_state.messages.pop()
            return

        citations = done.get("citations") or []
        if doc:
            status.update(label=f"📄 Đã đối chiếu tài liệu «{doc['name']}»", state="complete")
            status.write(f"✓ Trích {len(citations)} đoạn liên quan nhất để trả lời")
        elif done.get("out_of_scope"):
            status.update(label="ℹ️ Câu hỏi nằm ngoài phạm vi 1945", state="complete")
        else:
            status.update(label=f"📚 Đã tìm thấy {len(citations)} nguồn liên quan", state="complete")
            status.write("✓ Đã tạo câu trả lời từ các nguồn trên")

        answer = done.get("answer") or buffer
        placeholder.markdown(answer)
        message = {
            "role": "assistant",
            "content": answer,
            "citations": citations,
            "subgraph": done.get("subgraph") or {},
            "timeline": done.get("timeline") or [],
            "significance": done.get("significance") or "",
            "out_of_scope": bool(done.get("out_of_scope")),
        }
        st.session_state.messages.append(message)
        render_answer(message, key_prefix=f"ans{len(st.session_state.messages)}")


def render() -> None:
    init_state()
    _header()
    st.divider()

    has_chat = bool(st.session_state.messages) or bool(st.session_state.get("pending_q"))
    left, right = st.columns([3, 1.4], gap="large") if has_chat else (st.container(), None)

    with left:
        if not st.session_state.messages and not st.session_state.get("pending_q"):
            _welcome()
        for i, msg in enumerate(st.session_state.messages):
            avatar = ASSISTANT_AVATAR if msg["role"] == "assistant" else None
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])
                if msg["role"] == "assistant":
                    render_answer(msg, key_prefix=f"hist{i}")

        question = st.session_state.pop("pending_q", None)
        if question:
            _ask(question)

    if right is not None:
        with right:
            st.markdown("#### 🧭 Ngữ cảnh lịch sử")
            last = next((m for m in reversed(st.session_state.messages) if m["role"] == "assistant"), None)
            if last and last.get("subgraph"):
                context_panel(last["subgraph"], key_prefix="ctx")
            else:
                st.caption("Khi bạn hỏi về một sự kiện, chi tiết về thời gian, địa điểm và nhân vật sẽ hiện ở đây.")

    attach_controls()
    typed = st.chat_input("Hỏi Việt Sử AI về lịch sử Việt Nam...")
    if typed:
        _ask(typed)
        st.rerun()


def sidebar_recent() -> None:
    st.markdown("**Lịch sử gần đây**")
    for q in recent_questions():
        st.markdown(f"<span class='vs-muted'>💬 {q}</span>", unsafe_allow_html=True)
