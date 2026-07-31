"""FastAPI entrypoint: health, ingest, query."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import agent_api, config, ingest as ingest_mod, llm, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rag.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Chroma and (optionally) ingest before serving traffic."""
    try:
        store.connect()
    except Exception as exc:  # noqa: BLE001 - surface via /api/health instead of crash-looping
        log.error("startup: chroma unavailable: %s", exc)

    # Hand the agent wrapper this app's retriever, so its policy lookups run
    # in-process instead of looping back over HTTP.
    agent_api.set_retriever(_retrieve)

    if config.AUTO_INGEST:
        try:
            log.info("startup ingest: %s", ingest_mod.ingest())
        except FileNotFoundError as exc:
            log.warning("startup ingest skipped: %s", exc)
        except Exception as exc:  # noqa: BLE001
            log.error("startup ingest failed: %s", exc)
    yield


app = FastAPI(title="RAG API", version="1.0.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        count = store.collection().count()
        chroma_ok = True
    except Exception as exc:  # noqa: BLE001
        log.warning("health: chroma unreachable: %s", exc)
        count, chroma_ok = 0, False
    return {
        "status": "ok" if chroma_ok else "degraded",
        "chroma_connected": chroma_ok,
        "collection": config.CHROMA_COLLECTION,
        "chunks_indexed": count,
        "embedding_model": config.EMBEDDING_MODEL,
        "ai_configured": llm.configured(),
        "ai_model": llm.models()[0] if llm.configured() and llm.models() else None,
    }


@app.post("/api/ingest")
def run_ingest() -> dict[str, Any]:
    try:
        return ingest_mod.ingest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("ingest failed")
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}") from exc


def _retrieve(question: str, top_k: int) -> list[dict[str, Any]]:
    coll = store.collection()
    if coll.count() == 0:
        return []
    result = coll.query(
        query_texts=[question],
        n_results=min(top_k, coll.count()),
        include=["documents", "metadatas", "distances"],
    )
    chunks: list[dict[str, Any]] = []
    for cid, doc, meta, dist in zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    ):
        meta = meta or {}
        chunks.append({
            "id": cid,
            "content": doc,
            "title": meta.get("title"),
            "section": meta.get("section"),
            "source_file": meta.get("source_file"),
            "source_pointer": meta.get("source_pointer"),
            # cosine distance -> similarity, for a human-readable score
            "score": round(1.0 - float(dist), 4),
        })
    return chunks


@app.post("/api/query")
def query(request: QueryRequest) -> dict[str, Any]:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        chunks = _retrieve(question, request.top_k or config.TOP_K)
    except Exception as exc:  # noqa: BLE001
        log.exception("retrieval failed")
        raise HTTPException(status_code=503, detail=f"retrieval failed: {exc}") from exc

    generated = llm.generate_answer(question, chunks)
    return {
        "question": question,
        "answer": generated["answer"],
        "mode": generated["mode"],
        "warning": generated["warning"],
        "model": generated["model"],
        "sources": [
            {k: c[k] for k in ("id", "title", "section", "source_file", "source_pointer", "score")}
            for c in chunks
        ],
    }


# Alias so either documented path works.
@app.post("/api/chat")
def chat(request: QueryRequest) -> dict[str, Any]:
    return query(request)


class AgentRequest(BaseModel):
    mode: str = Field(default="daily", pattern="^(daily|weekly)$")
    query: str | None = Field(default=None, max_length=2000)
    top_n: int = Field(default=10, ge=1, le=50)


@app.post("/api/agent")
def run_agent(request: AgentRequest) -> dict[str, Any]:
    """Run the progress agent and return its fixed 7-key JSON, unaltered.

    Defined with `def` (not `async def`) so FastAPI runs the synchronous agent in
    a threadpool and the event loop stays free.
    """
    if not agent_api.available():
        raise HTTPException(status_code=503,
                            detail=f"agent unavailable: {agent_api.AGENT_IMPORT_ERROR}")
    try:
        return agent_api.run_agent(mode=request.mode, query=request.query,
                                   top_n=request.top_n)
    except Exception as exc:  # noqa: BLE001
        log.exception("agent run failed")
        raise HTTPException(status_code=500, detail=f"agent run failed: {exc}") from exc
