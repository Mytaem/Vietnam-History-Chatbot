"""Chọn bài theo profile: seed + category + 1-hop → lọc P31/năm/1945 → gán period, tier. (M3)"""
from __future__ import annotations


def collect(profile: str) -> None:
    """Ghi data/raw/<period_id>/articles.jsonl và data/reports/missing_seeds.txt."""
    raise NotImplementedError


def assign_period(article: dict) -> tuple[str, list[str]]:
    """→ (period_id chính, period_ids giao nhau)."""
    raise NotImplementedError


def assign_tier(articles: list[dict], quota: int) -> None:
    """Seed trước, còn thiếu lấy theo in-link → tier A, còn lại B."""
    raise NotImplementedError
