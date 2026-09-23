"""Nạp đồ thị: Era/Period (PART_OF, NEXT) → backbone → Article/Chunk/Entity/Relation
→ MENTIONS, IN_PERIOD, degree, display_name. (M5)"""
from __future__ import annotations


def load_periods(store, eras) -> None:
    raise NotImplementedError


def load_backbone(store, backbone_dir: str) -> None:
    raise NotImplementedError


def load_resolved(store, resolved_dir: str) -> None:
    raise NotImplementedError


def link_periods(store) -> None:
    """Tạo (:Entity)-[:IN_PERIOD]->(:Period) theo overlap năm."""
    raise NotImplementedError


def compute_degree_and_display_names(store) -> None:
    raise NotImplementedError
