"""Thành phần UI: vẽ subgraph (streamlit-agraph), timeline theo màu era, thẻ nguồn. (M7)"""


def render_graph(subgraph: dict) -> None:
    raise NotImplementedError


def render_timeline(events: list[dict], eras: list[dict]) -> None:
    raise NotImplementedError


def render_sources(citations: list[dict]) -> None:
    raise NotImplementedError
