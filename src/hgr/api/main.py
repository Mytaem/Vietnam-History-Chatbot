"""FastAPI: /chat (SSE), /retrieve, /periods, /entity/{id}, /health, /stats. (M7)"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from hgr import __version__
from hgr.api.models import ChatRequest, RetrieveRequest
from hgr.config import get_settings
from hgr.generate.answerer import answer as generate_answer
from hgr.generate.context_builder import build_context
from hgr.graph.store import Neo4jStore
from hgr.llm.ollama_client import OllamaClient
from hgr.periods import load_eras
from hgr.retrieve.pipeline import retrieve


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.store = Neo4jStore(s.neo4j.uri, s.neo4j.user, s.neo4j.password, s.neo4j.database)
    app.state.client = OllamaClient(s.llm.host, s.llm.chat_model, s.llm.embed_model, num_ctx=s.llm.num_ctx,
                                     timeout_s=s.llm.timeout_s)
    yield
    app.state.store.close()


app = FastAPI(title="History GraphRAG", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _retrieval_result_dict(result) -> dict:
    return {
        "plan": result.plan.model_dump() if result.plan else None,
        "top_chunks": result.top_chunks,
        "triplets": result.triplets,
        "paths": result.paths,
        "subgraph": result.subgraph,
        "out_of_scope": result.out_of_scope,
    }


@app.get("/health")
def health() -> dict:
    s = get_settings()
    neo4j_ok = app.state.store.ping()
    try:
        models = app.state.client.list_models()
        ollama_ok = True
    except Exception:
        models, ollama_ok = [], False

    def pulled(name: str) -> bool:
        base = name.split(":")[0]
        return any(m == name or m.split(":")[0] == base for m in models)

    return {
        "status": "ok" if neo4j_ok and ollama_ok else "degraded",
        "version": __version__,
        "neo4j": neo4j_ok,
        "ollama": ollama_ok,
        "chat_model_pulled": pulled(s.llm.chat_model) if ollama_ok else False,
        "embed_model_pulled": pulled(s.llm.embed_model) if ollama_ok else False,
    }


@app.post("/retrieve")
def retrieve_endpoint(req: RetrieveRequest) -> dict:
    result = retrieve(req.question, req.history, req.period_filter, req.mode,
                       store=app.state.store, client=app.state.client)
    return _retrieval_result_dict(result)


@app.post("/chat")
async def chat(req: ChatRequest):
    from hgr.generate.answerer import NO_DATA_MSG, OUT_OF_SCOPE_MSG

    async def event_stream():
        result = retrieve(req.question, req.history, req.period_filter, req.mode,
                           store=app.state.store, client=app.state.client)
        if result.out_of_scope:
            yield {"event": "done", "data": json.dumps({
                "answer": OUT_OF_SCOPE_MSG, "citations": [], "subgraph": {}, "timeline": [], "out_of_scope": True,
            }, ensure_ascii=False)}
            return

        context, citations = build_context(result)
        yield {"event": "plan", "data": result.plan.model_dump_json() if result.plan else "{}"}

        full_answer = ""
        if not citations:
            full_answer = NO_DATA_MSG
            yield {"event": "token", "data": full_answer}
        else:
            for token in generate_answer(req.question, context, app.state.client, req.history):
                full_answer += token
                yield {"event": "token", "data": token}

        timeline = sorted(
            {(n["start_year"], n.get("display_name") or n.get("name"))
             for n in result.subgraph.get("nodes", []) if n.get("start_year") is not None}
        )
        yield {"event": "done", "data": json.dumps({
            "answer": full_answer,
            "citations": citations,
            "subgraph": result.subgraph,
            "timeline": [{"year": y, "label": label} for y, label in timeline],
            "out_of_scope": False,
        }, ensure_ascii=False)}

    return EventSourceResponse(event_stream())


@app.get("/periods")
def periods_tree() -> dict:
    rows = app.state.store.run(
        "MATCH (p:Period) OPTIONAL MATCH (e:Entity)-[:IN_PERIOD]->(p) "
        "RETURN p.id AS id, count(DISTINCT e) AS entity_count"
    )
    counts = {r["id"]: r["entity_count"] for r in rows}
    eras = []
    for era in load_eras():
        eras.append({
            "id": era.id, "name": era.name, "start": era.start, "end": era.end, "color": era.color,
            "periods": [
                {"id": p.id, "name": p.name, "start": p.start, "end": p.end, "parallel": p.parallel,
                 "legendary": p.legendary, "disputed": p.disputed, "entity_count": counts.get(p.id, 0)}
                for p in era.periods
            ],
        })
    return {"eras": eras}


@app.get("/periods/{period_id}")
def period_detail(period_id: str) -> dict:
    from hgr.periods import all_periods

    period = next((p for p in all_periods() if p.id == period_id), None)
    if period is None:
        raise HTTPException(404, f"Không có giai đoạn '{period_id}'")
    top_entities = app.state.store.run(
        "MATCH (p:Period {id: $id}) MATCH (e:Entity)-[:IN_PERIOD]->(p) "
        "RETURN e.id AS id, e.display_name AS name, head([l IN labels(e) WHERE l <> 'Entity'] + ['Entity']) AS type, "
        "e.start_year AS start_year, e.degree AS degree ORDER BY degree DESC LIMIT 15",
        id=period_id,
    )
    neighbours = app.state.store.run(
        "MATCH (p:Period {id: $id}) OPTIONAL MATCH (prev:Period)-[:NEXT]->(p) "
        "OPTIONAL MATCH (p)-[:NEXT]->(nxt:Period) RETURN prev.id AS prev, nxt.id AS next LIMIT 1",
        id=period_id,
    )
    nb = neighbours[0] if neighbours else {"prev": None, "next": None}
    return {
        "id": period.id, "name": period.name, "start": period.start, "end": period.end,
        "legendary": period.legendary, "disputed": period.disputed,
        "prev_period": nb["prev"], "next_period": nb["next"],
        "top_entities": top_entities,
    }


@app.get("/entity/{entity_id}")
def entity_detail(entity_id: str) -> dict:
    rows = app.state.store.run(
        "MATCH (e:Entity {id: $id}) "
        "OPTIONAL MATCH (e)-[r]-(n:Entity) "
        "RETURN e {.*, type: head([l IN labels(e) WHERE l <> 'Entity'] + ['Entity'])} AS entity, "
        "collect(DISTINCT {id: n.id, name: n.display_name, type: head([l IN labels(n) WHERE l <> 'Entity'] + ['Entity']), "
        "rel: type(r)})[0..30] AS neighbours",
        id=entity_id,
    )
    if not rows or rows[0]["entity"] is None:
        raise HTTPException(404, f"Không có entity '{entity_id}'")
    row = rows[0]
    entity = {k: v for k, v in row["entity"].items() if k != "embedding"}
    return {"entity": entity, "neighbours": [n for n in row["neighbours"] if n["id"]]}


@app.get("/stats")
def stats() -> dict:
    by_label = app.state.store.run("MATCH (n) RETURN labels(n) AS labels, count(*) AS count")
    by_period = app.state.store.run(
        "MATCH (p:Period) OPTIONAL MATCH (e:Entity)-[:IN_PERIOD]->(p) "
        "RETURN p.id AS period, count(DISTINCT e) AS entities ORDER BY period"
    )
    return {"by_label": by_label, "by_period": by_period}
