"""retrieve(question, history, period_filter) → RetrievalResult (PLAN.md 6.3). (M6)"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from hgr.config import get_settings
from hgr.log import get_logger
from hgr.retrieve import chunk_search, graph_search, linker, period_rules
from hgr.retrieve.analyzer import QueryPlan, analyze
from hgr.retrieve.fusion import boost_evidence, rerank, rrf
from hgr.retrieve.graph_search import Subgraph

log = get_logger(__name__)


@dataclass
class RetrievalResult:
    plan: QueryPlan | None = None
    top_chunks: list[dict] = field(default_factory=list)
    triplets: list[dict] = field(default_factory=list)
    paths: list[dict] = field(default_factory=list)
    subgraph: dict = field(default_factory=dict)
    out_of_scope: bool = False


def _default_store():
    from hgr.graph.store import Neo4jStore

    s = get_settings().neo4j
    return Neo4jStore(s.uri, s.user, s.password, s.database)


def _default_client():
    from hgr.llm.ollama_client import OllamaClient

    s = get_settings().llm
    return OllamaClient(s.host, s.chat_model, s.embed_model, num_ctx=s.num_ctx, timeout_s=s.timeout_s)


def _chunks_by_ids(store, ids) -> list[dict]:
    if not ids:
        return []
    rows = store.run(
        "MATCH (c:Chunk) WHERE c.id IN $ids RETURN c.id AS id, c.text AS text, c.header AS header, "
        "c.page_title AS page_title, c.section_path AS section_path, c.min_year AS min_year, "
        "c.max_year AS max_year, c.legendary AS legendary",
        ids=list(ids),
    )
    return [dict(r) for r in rows]


def _max_degree(store, setting) -> int | None:
    if setting is None:
        return None
    if isinstance(setting, (int, float)):
        return int(setting)
    row = store.run("MATCH (e:Entity) WHERE e.degree IS NOT NULL RETURN percentileDisc(e.degree, 0.99) AS p99")
    return row[0]["p99"] if row and row[0]["p99"] is not None else None


def retrieve(
    question: str,
    history: list[dict] | None = None,
    period_filter: tuple[int, int] | None = None,
    mode: str = "graphrag",
    store=None,
    client=None,
) -> RetrievalResult:
    settings = get_settings().retrieval
    owns_store = store is None
    store = store or _default_store()
    client = client or _default_client()
    try:
        rules = period_rules.parse(question)
        if rules.out_of_scope:
            return RetrievalResult(out_of_scope=True)

        plan = analyze(question, history or [], client)
        plan.time_range = rules.time_range or period_filter or plan.time_range
        if not plan.periods:
            if rules.periods:
                plan.periods = rules.periods
            elif plan.time_range:
                from hgr.periods import periods_for_range

                plan.periods = [p.id for p in periods_for_range(*plan.time_range)]

        query_text = plan.rewritten or question
        seeds = linker.link_all(plan.entities, store, client, prefer_periods=plan.periods or None)
        if not seeds and plan.periods:
            seeds = graph_search.period_seeds(plan.periods, store, top=10)

        top_k = settings.overview_top_chunks if plan.intent == "overview" else settings.top_chunks
        chunks_v = chunk_search.search(
            query_text, store, client, k=settings.chunk_k, years=plan.time_range, periods=plan.periods or None
        )

        triplets: list[dict] = []
        paths_result: list[dict] = []
        subgraph = Subgraph()
        graph_chunks: list[dict] = []
        path_chunks: list[dict] = []

        if mode == "graphrag" and seeds:
            max_degree = _max_degree(store, settings.max_degree)
            # Không lọc theo plan.rel_hints: đó là LLM đoán 1-2 loại quan hệ, dùng làm bộ lọc CỨNG sẽ làm
            # truy hồi ra rỗng bất cứ khi nào LLM đoán thiếu/sai hoặc cạnh thật thuộc loại khác. local()
            # tự giới hạn về quan hệ tri thức thật trong ontology (loại IN_PERIOD/MENTIONS/...) là đủ.
            sub = graph_search.local(seeds, store, hops=settings.hops, years=plan.time_range, max_degree=max_degree)
            ranked = graph_search.ppr(sub, seeds, top_n=settings.ppr_top_n, alpha=settings.ppr_alpha)
            triplets = ranked.triplets
            graph_chunks = _chunks_by_ids(store, ranked.evidence_chunk_ids)
            subgraph = sub.trim(list(dict.fromkeys(ranked.node_ids + seeds)))

            if plan.intent == "relational" and len(seeds) >= 2:
                paths_result = graph_search.paths(seeds[0], seeds[1], store)
                path_evidence = {cid for p in paths_result for e in p["edges"] for cid in e.get("evidence_chunk_ids", [])}
                path_chunks = _chunks_by_ids(store, path_evidence)
                for p in paths_result:
                    for node in p["nodes"]:
                        subgraph.nodes.setdefault(node["id"], node)
                    for edge in p["edges"]:
                        subgraph.edges.setdefault(edge["id"], edge)

        weights = settings.fusion.get(plan.intent, [0.5, 0.5, 0.0]) if mode == "graphrag" else [1.0, 0.0, 0.0]
        fused = rrf([chunks_v, graph_chunks, path_chunks], weights=weights, k=settings.rrf_k)
        evidence_ids = {c["id"] for c in graph_chunks} | {c["id"] for c in path_chunks}
        fused = boost_evidence(fused, evidence_ids, factor=settings.evidence_boost)
        if settings.rerank:
            fused = rerank(question, fused[:30], model=settings.rerank_model)

        return RetrievalResult(
            plan=plan,
            top_chunks=fused[:top_k],
            triplets=triplets,
            paths=paths_result,
            subgraph=subgraph.as_dict(),
            out_of_scope=False,
        )
    finally:
        if owns_store:
            store.close()
