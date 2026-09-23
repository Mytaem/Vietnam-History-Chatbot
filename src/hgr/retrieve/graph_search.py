"""Graph retrieval: k-hop subgraph, Personalized PageRank (networkx), path A↔B, period seed. (M6)"""
from __future__ import annotations


def local(seeds: list[str], hops: int = 2, rel_types: list[str] | None = None,
          years: tuple[int, int] | None = None, max_degree: int | None = None):
    raise NotImplementedError


def ppr(subgraph, seeds: list[str], top_n: int = 25, alpha: float = 0.85):
    raise NotImplementedError


def paths(a: str, b: str, max_hops: int = 4, limit: int = 5):
    raise NotImplementedError


def period_seeds(periods: list[str], top: int = 10) -> list[str]:
    raise NotImplementedError
