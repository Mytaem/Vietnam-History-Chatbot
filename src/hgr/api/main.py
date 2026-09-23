"""FastAPI: /chat (SSE), /retrieve, /periods, /entity/{id}, /health, /stats. (M7)"""
from fastapi import FastAPI

from hgr import __version__

app = FastAPI(title="History GraphRAG", version=__version__)


@app.get("/health")
def health() -> dict:
    # TODO(M1): kiểm tra Neo4j + Ollama + model
    return {"status": "scaffold", "version": __version__}

# TODO(M7): POST /chat (SSE), POST /retrieve, GET /periods, GET /periods/{id},
#           GET /entity/{id}, GET /stats
