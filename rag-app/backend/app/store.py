"""Chroma connection + the embedding model. Both are created once and reused."""
from __future__ import annotations

import logging
import time

import chromadb
from chromadb.utils import embedding_functions

from app import config

log = logging.getLogger("rag.store")

_client: chromadb.ClientAPI | None = None
_collection = None


def _embedding_function():
    """SentenceTransformer runs locally — no embedding API key required."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=config.EMBEDDING_MODEL
    )


def connect(retries: int = 30, delay: float = 2.0):
    """Get (or lazily create) the collection, retrying until Chroma accepts connections.

    The compose healthcheck only proves the TCP port is open, so the backend
    retries here as well — this is what makes `docker compose up` order-independent.
    """
    global _client, _collection
    if _collection is not None:
        return _collection

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            _client = chromadb.HttpClient(host=config.CHROMA_HOST, port=config.CHROMA_PORT)
            _client.heartbeat()
            _collection = _client.get_or_create_collection(
                name=config.CHROMA_COLLECTION,
                embedding_function=_embedding_function(),
                metadata={"hnsw:space": "cosine"},
            )
            log.info(
                "connected to chroma at %s:%s (collection=%s)",
                config.CHROMA_HOST, config.CHROMA_PORT, config.CHROMA_COLLECTION,
            )
            return _collection
        except Exception as exc:  # noqa: BLE001 - retry on any startup failure
            last_error = exc
            log.warning("chroma not ready (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(delay)

    raise RuntimeError(f"could not reach chroma after {retries} attempts: {last_error}")


def collection():
    return connect()
