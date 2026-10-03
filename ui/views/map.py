"""Bản đồ lịch sử: chỉ hiển thị địa danh có tọa độ đã được xác minh từ Wikidata."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from api import ApiUnavailable, list_entities
from views.browse import render_browse


def render() -> None:
    st.markdown("## Bản đồ lịch sử")
    st.markdown(
        "<span class='vs-muted'>Các địa danh có tọa độ được lấy từ Wikidata và đối chiếu với tên trong dữ liệu.</span>",
        unsafe_allow_html=True,
    )
    try:
        places = list_entities("Place", None, limit=300)
    except ApiUnavailable:
        st.error("Chưa tải được dữ liệu bản đồ lúc này. Vui lòng thử lại sau.")
        return

    located = [p for p in places if p.get("lat") is not None and p.get("lon") is not None]
    if located:
        df = pd.DataFrame(located)[["name", "lat", "lon"]]
        st.map(df, latitude="lat", longitude="lon", size=60)
        st.caption(f"Đang hiển thị {len(located)} trên tổng số {len(places)} địa danh.")
    else:
        st.info(
            "Chưa có địa danh nào có tọa độ đã xác minh trong dữ liệu hiện tại, nên bản đồ còn trống. "
            "Các địa danh bên dưới vẫn đầy đủ trong danh sách."
        )

    render_browse(
        "Danh sách địa danh",
        "Tất cả địa danh trong dữ liệu. Bấm Xem chi tiết để biết địa danh liên quan đến những gì.",
        "Place",
        key="plc",
    )
