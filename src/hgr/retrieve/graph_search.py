"""Graph retrieval: k-hop subgraph, Personalized PageRank (networkx), path A↔B, period seed. (M6)"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from hgr.extract.schemas import RelType

# Chỉ đi theo quan hệ tri thức Entity↔Entity trong ontology. Nếu không lọc type(x), truy hồi sẽ lạc qua
# các node bậc rất cao như :Period/:Chunk/:Article (IN_PERIOD, MENTIONS, HAS_CHUNK, ABOUT, PART_OF, NEXT),
# làm PPR xếp sai hẳn (period/chunk hub thắng áp đảo thực thể thật).
ONTOLOGY_RELS = list(RelType.__args__)

_NODE_PROJ = (
    # Entity có 2 nhãn (Entity + nhãn con cụ thể như Person/Place...); lấy nhãn con để tô màu/UI đúng loại.
    "{id: node.id, name: node.name, display_name: node.display_name, "
    "type: head([l IN labels(node) WHERE l <> 'Entity'] + ['Entity']), "
    "start_year: node.start_year, end_year: node.end_year, legendary: node.legendary, "
    "disputed: node.disputed, degree: node.degree}"
)
_REL_PROJ = (
    "{id: elementId(rel), type: type(rel), source_id: startNode(rel).id, target_id: endNode(rel).id, "
    "role: rel.role, side: rel.side, start_year: rel.start_year, end_year: rel.end_year, "
    "confidence: rel.confidence, source: rel.source, evidence_chunk_ids: coalesce(rel.evidence_chunk_ids, [])}"
)


@dataclass
class Subgraph:
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: dict[str, dict] = field(default_factory=dict)

    def trim(self, node_ids: list[str]) -> "Subgraph":
        keep = set(node_ids)
        edges = {eid: e for eid, e in self.edges.items() if e["source_id"] in keep and e["target_id"] in keep}
        return Subgraph(nodes={nid: n for nid, n in self.nodes.items() if nid in keep}, edges=edges)

    def as_dict(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())}

    def to_networkx(self) -> nx.Graph:
        graph = nx.Graph()
        for node_id in self.nodes:
            graph.add_node(node_id)
        for edge in self.edges.values():
            if edge["source_id"] in self.nodes and edge["target_id"] in self.nodes:
                graph.add_edge(edge["source_id"], edge["target_id"], **edge)
        return graph


@dataclass
class PPRResult:
    node_ids: list[str] = field(default_factory=list)
    triplets: list[dict] = field(default_factory=list)
    evidence_chunk_ids: set[str] = field(default_factory=set)


def local(seeds: list[str], store, hops: int = 2, rel_types: list[str] | None = None,
          years: tuple[int, int] | None = None, max_degree: int | None = None) -> Subgraph:
    """k-hop subgraph quanh `seeds`, lọc theo rel_types/năm/degree hub (PLAN.md 6.3)."""
    if not seeds:
        return Subgraph()
    hops = max(1, min(int(hops), 4))
    rels = rel_types or ONTOLOGY_RELS
    cypher = f"""
    MATCH (s:Entity) WHERE s.id IN $seeds
    MATCH path = (s)-[r*1..{hops}]-(n:Entity)
    WHERE all(x IN r WHERE type(x) IN $rels
          AND ($y0 IS NULL OR x.start_year IS NULL
               OR (x.start_year <= $y1 + 5 AND coalesce(x.end_year, x.start_year) >= $y0 - 5)))
      AND all(m IN nodes(path)[1..] WHERE $maxdeg IS NULL OR coalesce(m.degree, 0) <= $maxdeg)
    WITH path LIMIT 400
    RETURN [node IN nodes(path) | {_NODE_PROJ}] AS nodes,
           [rel IN relationships(path) | {_REL_PROJ}] AS rels
    """
    rows = store.run(
        cypher, seeds=seeds, rels=rels,
        y0=years[0] if years else None, y1=years[1] if years else None, maxdeg=max_degree,
    )
    sub = Subgraph()
    for row in rows:
        for node in row["nodes"]:
            sub.nodes[node["id"]] = node
        for rel in row["rels"]:
            sub.edges[rel["id"]] = rel
    return sub


def ppr(subgraph: Subgraph, seeds: list[str], top_n: int = 25, alpha: float = 0.85) -> PPRResult:
    """Personalized PageRank quanh seeds; trả về node nổi bật nhất + cạnh/evidence liên quan."""
    graph = subgraph.to_networkx()
    present_seeds = [s for s in seeds if s in graph]
    if not graph.number_of_nodes() or not present_seeds:
        return PPRResult()
    personalization = {s: 1.0 / len(present_seeds) for s in present_seeds}
    try:
        scores = nx.pagerank(graph, alpha=alpha, personalization=personalization)
    except nx.PowerIterationFailedConvergence:
        scores = {n: 1.0 for n in graph}
    node_ids = [n for n, _ in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:top_n]]
    keep = set(node_ids) | set(present_seeds)
    triplets = [e for e in subgraph.edges.values() if e["source_id"] in keep and e["target_id"] in keep]
    evidence = {cid for t in triplets for cid in t.get("evidence_chunk_ids", [])}
    return PPRResult(node_ids=node_ids, triplets=triplets, evidence_chunk_ids=evidence)


def paths(a: str, b: str, store, max_hops: int = 4, limit: int = 5) -> list[dict]:
    """Đường đi ngắn nhất A↔B, loại các node hub để không đi qua các nước/triều đại quá chung."""
    max_hops = max(1, min(int(max_hops), 6))
    rows = store.run(
        f"""
        MATCH (a:Entity {{id: $a}}), (b:Entity {{id: $b}})
        MATCH path = allShortestPaths((a)-[r*..{max_hops}]-(b))
        WHERE all(x IN r WHERE type(x) IN $rels)
          AND all(m IN nodes(path)[1..-1] WHERE coalesce(m.degree, 0) <= 200)
        RETURN [node IN nodes(path) | {_NODE_PROJ}] AS nodes,
               [rel IN relationships(path) | {_REL_PROJ}] AS rels
        LIMIT $limit
        """,
        a=a, b=b, rels=ONTOLOGY_RELS, limit=limit,
    )
    return [{"nodes": row["nodes"], "edges": row["rels"]} for row in rows]


def period_seeds(periods: list[str], store, top: int = 10) -> list[str]:
    """Entity bậc cao nhất thuộc các giai đoạn (dùng cho câu hỏi tổng quan, không link được thực thể cụ thể)."""
    if not periods:
        return []
    rows = store.run(
        "MATCH (p:Period) WHERE p.id IN $periods MATCH (e:Entity)-[:IN_PERIOD]->(p) "
        "RETURN DISTINCT e.id AS id, e.degree AS degree ORDER BY degree DESC LIMIT $top",
        periods=periods, top=top,
    )
    return [r["id"] for r in rows]
