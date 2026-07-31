"""Thin HTTP wrapper around the progress agent.

The agent is a plain Python package that reads the SSOT directly. This module is
the only glue needed to expose it over the existing backend — it adds no logic of
its own and changes nothing inside `agent/`.

One substitution happens here: `agent.tools.search_policy` normally reaches the
RAG backend over HTTP. Since the agent now runs *inside* that backend, an HTTP
call to itself would be a needless round trip (and would block a single-worker
event loop). So the tool is swapped for an in-process call to this app's own
retriever. That is dependency injection at a boundary the agent already exposes,
not a change to agent logic.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger("rag.agent_api")

_retrieve_fn: Callable[[str, int], list[dict]] | None = None

try:
    from agent import agent as agent_core
    from agent import tools as agent_tools
    AGENT_IMPORT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001 - agent not mounted; report, don't crash
    agent_core = agent_tools = None  # type: ignore[assignment]
    AGENT_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
    log.warning("agent package unavailable: %s", AGENT_IMPORT_ERROR)


def set_retriever(fn: Callable[[str, int], list[dict]]) -> None:
    """Give the wrapper the app's own retrieval function (called once at startup)."""
    global _retrieve_fn
    _retrieve_fn = fn


def _in_process_search_policy(query: str, top_k: int = 3) -> dict:
    """Drop-in for agent.tools.search_policy, backed by local Chroma retrieval."""
    if _retrieve_fn is None:
        return {"ok": False, "query": query, "results": [],
                "error": "retriever not wired"}
    try:
        chunks = _retrieve_fn(query, top_k)
    except Exception as exc:  # noqa: BLE001 - degrade exactly like the HTTP version
        return {"ok": False, "query": query, "results": [],
                "error": f"local retrieval failed: {type(exc).__name__}"}
    return {
        "ok": True, "query": query, "error": None, "mode": "in_process",
        "results": [
            {"title": c.get("title"), "score": c.get("score"),
             "ref": f"{c.get('source_file', '')}{c.get('source_pointer', '')}"}
            for c in chunks
        ],
    }


if agent_tools is not None:
    agent_tools.search_policy = _in_process_search_policy  # installed once, at import


def available() -> bool:
    return agent_core is not None


def status() -> dict[str, Any]:
    if agent_core is None:
        return {"available": False, "error": AGENT_IMPORT_ERROR}
    return {"available": True, "ssot_db_path": agent_tools.SSOT_DB_PATH,
            "tools": sorted(agent_tools.TOOLS)}


def run_agent(mode: str = "daily", query: str | None = None, top_n: int = 10) -> dict:
    """Run one agent pass. Returns the agent's fixed 7-key dict, unaltered."""
    if agent_core is None:
        raise RuntimeError(f"agent package not importable: {AGENT_IMPORT_ERROR}")
    return agent_core.run(mode=mode, query=query, top_n=top_n)
