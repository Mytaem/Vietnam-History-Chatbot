"""Lớp gọi API FastAPI của hệ thống. Mọi dữ liệu trên giao diện đều lấy từ đây."""
from __future__ import annotations

import json
import os
from collections.abc import Iterator

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")
OFFLINE_MSG = "Hệ thống hiện chưa sẵn sàng. Bạn vui lòng thử lại sau ít phút nhé."


class ApiUnavailable(Exception):
    pass


def _get(path: str, **params) -> dict:
    try:
        resp = httpx.get(f"{API_URL}{path}", params=params or None, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise ApiUnavailable(str(exc)) from exc


@st.cache_data(ttl=60, show_spinner=False)
def periods_tree() -> list[dict]:
    return _get("/periods").get("eras", [])


@st.cache_data(ttl=60, show_spinner=False)
def period_detail(period_id: str) -> dict:
    return _get(f"/periods/{period_id}")


@st.cache_data(ttl=60, show_spinner=False)
def period_items(period_id: str) -> list[dict]:
    return _get(f"/periods/{period_id}/items").get("items", [])


@st.cache_data(ttl=60, show_spinner=False)
def list_entities(entity_type: str | None, q: str | None, limit: int = 60, period: str | None = None) -> list[dict]:
    return _get("/entities", type=entity_type, q=q, limit=limit, period=period).get("items", [])


@st.cache_data(ttl=60, show_spinner=False)
def entity_detail(entity_id: str) -> dict:
    return _get(f"/entity/{entity_id}")


@st.cache_data(ttl=60, show_spinner=False)
def entity_passages(entity_id: str, limit: int = 6) -> list[dict]:
    return _get(f"/entity/{entity_id}/passages", limit=limit).get("items", [])


@st.cache_data(ttl=30, show_spinner=False)
def health() -> dict:
    try:
        return _get("/health")
    except ApiUnavailable:
        return {"status": "down"}


def _sse(path: str, payload: dict) -> Iterator[tuple[str, object]]:
    """Phát các sự kiện SSE: ('plan', dict) | ('token', str) | ('done', dict)."""
    try:
        with httpx.stream("POST", f"{API_URL}{path}", json=payload, timeout=240) as resp:
            resp.raise_for_status()
            event, data_lines = None, []
            for raw in resp.iter_lines():
                line = raw if isinstance(raw, str) else raw.decode("utf-8")
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
                elif line == "":
                    data = "\n".join(data_lines)
                    data_lines = []
                    if event == "plan" and data:
                        yield "plan", json.loads(data)
                    elif event == "token":
                        yield "token", data
                    elif event == "done":
                        yield "done", json.loads(data)
                    event = None
    except Exception as exc:
        raise ApiUnavailable(str(exc)) from exc


def stream_chat(question: str, history: list[dict], period_filter) -> Iterator[tuple[str, object]]:
    payload: dict = {"question": question, "history": history}
    if period_filter:
        payload["period_filter"] = list(period_filter)
    return _sse("/chat", payload)


def stream_document(question: str, document_name: str, document_text: str,
                    history: list[dict]) -> Iterator[tuple[str, object]]:
    payload = {"question": question, "document_name": document_name,
               "document_text": document_text, "history": history}
    return _sse("/document/ask", payload)
