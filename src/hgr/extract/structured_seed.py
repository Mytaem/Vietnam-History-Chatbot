"""Triplet không cần LLM: backbone (curated 1.0) + Wikidata + infobox (0.95). (M4)"""
from __future__ import annotations


def from_backbone(backbone_dir: str) -> list[dict]:
    raise NotImplementedError


def from_wikidata(article: dict) -> list[dict]:
    raise NotImplementedError


def from_infobox(article: dict, infobox_map: dict) -> list[dict]:
    raise NotImplementedError
