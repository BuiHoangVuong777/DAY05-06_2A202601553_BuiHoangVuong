"""All configuration comes from environment variables — no config files, no hardcoded hosts."""
from __future__ import annotations

import os

# --- Chroma ---------------------------------------------------------------
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "rag_chunks")

# --- Embeddings -----------------------------------------------------------
# Multilingual on purpose: the corpus is Vietnamese, and an English-only model
# (e.g. Chroma's default all-MiniLM-L6-v2) retrieves badly on it.
#
# This model is also symmetric — it needs no per-role prefixes. Avoid the e5
# family here (intfloat/multilingual-e5-*): those are trained with "query: " /
# "passage: " prefixes, and Chroma applies one embedding function to documents
# and queries alike, so the prefixes can't be set asymmetrically and retrieval
# quality silently drops.
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# --- Ingestion ------------------------------------------------------------
CHUNKS_PATH = os.getenv("CHUNKS_PATH", "/data/rag_chunks.jsonl")
AUTO_INGEST = os.getenv("AUTO_INGEST", "true").strip().lower() in {"1", "true", "yes"}

# --- Retrieval ------------------------------------------------------------
TOP_K = int(os.getenv("TOP_K", "5"))

# --- Answer generation (OpenAI) ------------------------------------------
# Empty key is supported: the app returns retrieved chunks with mode="fallback".
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
# Optional — set for Azure/OpenRouter/vLLM or any OpenAI-compatible gateway.
# Empty means the SDK's default (https://api.openai.com/v1).
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()
# MODEL_1 is tried first; MODEL_2 is the secondary used if MODEL_1 errors.
# Leave MODEL_2 empty to disable the retry.
OPENAI_MODEL_1 = os.getenv("OPENAI_MODEL_1", "gpt-4o-mini").strip()
OPENAI_MODEL_2 = os.getenv("OPENAI_MODEL_2", "").strip()
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "60"))
