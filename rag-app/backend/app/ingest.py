"""Read the chunk JSONL, upsert into Chroma, skip chunks whose content is unchanged.

The chunk file is produced by scripts/build_rag_chunks.py and already carries a
stable `id` and a content `hash`, which is exactly what idempotent upsert needs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app import config, store

log = logging.getLogger("rag.ingest")

# Chroma metadata values must be str | int | float | bool. Chunks carry lists
# (keywords) and nulls (cohort, week, ...), so both need flattening.
def _clean_metadata(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key == "content":
            continue  # stored as the document, not as metadata
        if value is None:
            continue  # Chroma rejects None
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif isinstance(value, list):
            joined = ", ".join(str(v) for v in value if v is not None)
            if joined:
                out[key] = joined
        else:
            out[key] = str(value)
    return out


def load_chunks(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"chunks file not found: {path}")
    records = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no} is not valid JSON: {exc}") from exc
        if not record.get("id") or not record.get("content"):
            raise ValueError(f"{path}:{line_no} is missing required 'id' or 'content'")
        records.append(record)
    return records


def ingest(path: str | Path | None = None) -> dict[str, Any]:
    """Upsert all chunks. Returns counts; safe to call repeatedly."""
    path = path or config.CHUNKS_PATH
    records = load_chunks(path)
    coll = store.collection()

    ids = [r["id"] for r in records]

    # Skip work only for chunks stored with BOTH the same content hash and the
    # same embedding model. Comparing the hash alone is not enough: swapping
    # EMBEDDING_MODEL leaves the old vectors in place and every chunk looks
    # "unchanged", so queries get embedded by one model and matched against
    # another. Same dimensionality means no error — just silently wrong results.
    existing: dict[str, tuple[Any, Any]] = {}
    try:
        stored = coll.get(ids=ids, include=["metadatas"])
        for cid, meta in zip(stored.get("ids", []), stored.get("metadatas", [])):
            if meta:
                existing[cid] = (meta.get("hash"), meta.get("embedding_model"))
    except Exception as exc:  # noqa: BLE001 - first run has nothing to compare
        log.warning("could not read existing chunks (treating all as new): %s", exc)

    def _is_current(record: dict[str, Any]) -> bool:
        found = existing.get(record["id"])
        return found is not None and found == (record.get("hash"), config.EMBEDDING_MODEL)

    pending = [r for r in records if not _is_current(r)]

    if pending:
        metadatas = []
        for record in pending:
            meta = _clean_metadata(record)
            meta["embedding_model"] = config.EMBEDDING_MODEL  # drives the check above
            metadatas.append(meta)
        coll.upsert(
            ids=[r["id"] for r in pending],
            documents=[_embed_text(r) for r in pending],
            metadatas=metadatas,
        )

    result = {
        "chunks_in_file": len(records),
        "upserted": len(pending),
        "skipped_unchanged": len(records) - len(pending),
        "collection": config.CHROMA_COLLECTION,
        "collection_count": coll.count(),
        "embedding_model": config.EMBEDDING_MODEL,
        "source": str(path),
    }
    log.info("ingest complete: %s", result)
    return result


def _embed_text(record: dict[str, Any]) -> str:
    """Text actually embedded: title + section + content.

    The titles carry real retrieval signal ("Demo Day", "Cách kiếm XP") that the
    body alone often lacks, so they are prepended rather than kept as metadata only.
    """
    parts = [record.get("title"), record.get("section"), record.get("content")]
    return "\n".join(p for p in parts if p)
