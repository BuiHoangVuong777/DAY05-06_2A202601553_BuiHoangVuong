#!/usr/bin/env python3
"""Convert codebase/data/rag/*.json into retrieval-optimized JSONL for vector DB ingestion.

Semantic chunking: one chunk per authored semantic unit (a week, a block, a section,
an operating note, an author-provided chunk). No fixed-size windowing, no overlap —
every source unit is already a coherent, self-contained topic.

Everything emitted is copied from the sources. Nothing is paraphrased or invented:
  - `content`   is a deterministic plain-text rendering of the source values.
  - `summary`   is EXTRACTIVE (first 1-2 content lines), never generated.
  - `status`    comes from the source where a source states one, else "active".
  - `created_at`/`updated_at` are filesystem mtimes — no source carries a timestamp.

Determinism: ids and hashes derive only from (source file, JSON pointer, NFC content).
No clock, no randomness, no dict-order dependence. Re-running yields byte-identical
`rag_chunks.jsonl`.

Usage:
    python3 scripts/build_rag_chunks.py
    python3 scripts/build_rag_chunks.py --input codebase/data/rag --output output
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0.0"

# Files that restate other files rather than owning their content. Losing ties to a
# standalone topic file keeps the richer copy (see rank_key / notes).
AGGREGATE_FILES = {"cohort3_knowledge_base.json"}

# Source status strings -> normalized lifecycle values.
STATUS_MAP = {
    "đã xong": "completed",
    "hiện tại": "active",
    "upcoming": "upcoming",
}

# Jaccard threshold above which two chunks are treated as restatements of each other.
# Set from the measured distribution, not by feel: across all kept pairs this corpus
# has exactly one similarity value between 0.35 and 1.0 that is not a restatement-free
# pair, and it is 0.6842 (knowledge-base week 3 vs master timeline week 3 — a genuine
# duplicate that reworded "Bắt tay vào code" to "Bắt đầu code" and dropped a clause).
# 0.65 captures it; `near_misses_below_threshold` in the report proves nothing else
# sits near the cut. Re-check that list if the corpus grows.
NEAR_DUP_THRESHOLD = 0.65

SUMMARY_MAX_LINES = 2
SUMMARY_MAX_CHARS = 300


# --------------------------------------------------------------------------- utils


def nfc(text: str) -> str:
    """Unicode-normalize so Vietnamese diacritics hash identically across sources."""
    return unicodedata.normalize("NFC", text)


def norm_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", nfc(text)).strip()


def norm_for_compare(text: str) -> str:
    """Casefold + strip punctuation, for near-duplicate token comparison only."""
    lowered = norm_for_hash(text).casefold()
    return re.sub(r"[^\w\s/+-]", " ", lowered)


def tokens(text: str) -> set[str]:
    return {tok for tok in norm_for_compare(text).split() if tok}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def sha256(text: str) -> str:
    return hashlib.sha256(nfc(text).encode("utf-8")).hexdigest()


def make_id(source_file: str, pointer: str) -> str:
    """Stable, readable, collision-safe: <file-stem>::<slug>::<digest8>."""
    stem = Path(source_file).stem
    slug = re.sub(r"[^a-z0-9]+", "-", pointer.casefold()).strip("-")[:60]
    digest = hashlib.sha256(f"{source_file}#{pointer}".encode("utf-8")).hexdigest()[:8]
    return f"{stem}::{slug}::{digest}"


def iso_mtime(path: Path) -> str:
    ts = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    return ts.replace(microsecond=0).isoformat()


def sentences(line: str) -> list[str]:
    """Split on sentence punctuation followed by whitespace + an uppercase-ish start.

    Deliberately conservative so tokens like `P-042.` and `c3-app-042.io.vn` survive.
    """
    parts = re.split(r"(?<=[.!?])\s+(?=[^\s])", line.strip())
    return [p for p in parts if p]


def extractive_summary(content: str) -> str:
    """First 1-2 lines of the chunk's own text. Extractive by construction."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        # Prose unit: take whole sentences.
        picked = sentences(lines[0])[:SUMMARY_MAX_LINES]
        summary = " ".join(picked)
    else:
        # List unit: join with "; " so the summary reads as an enumeration.
        picked = lines[:SUMMARY_MAX_LINES]
        summary = "; ".join(p.rstrip(".;") for p in picked)
        if len(lines) > SUMMARY_MAX_LINES:
            summary += "; …"
    if len(summary) > SUMMARY_MAX_CHARS:
        first = picked[0]
        summary = first if len(first) <= SUMMARY_MAX_CHARS else first[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return summary


def clean_keywords(*groups: Iterable[Any]) -> list[str]:
    """Merge keyword lists, preserving first-seen order, casefold-deduplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for kw in group or []:
            if not isinstance(kw, str):
                continue
            key = norm_for_hash(kw).casefold()
            if key and key not in seen:
                seen.add(key)
                out.append(norm_for_hash(kw))
    return out


# ------------------------------------------------------------------- content render


def render_item(item: Any) -> str:
    """Render one source content item to a plain-text line, losing no field."""
    if isinstance(item, str):
        return nfc(item.strip())
    if not isinstance(item, dict):
        return nfc(str(item).strip())

    # Discord command entries.
    if "command" in item:
        desc = str(item.get("description", "")).strip()
        return nfc(f"{item['command']} — {desc}" if desc else str(item["command"]))

    # XP level tiers.
    if "level" in item and "threshold_xp" in item:
        name = str(item.get("name", "")).strip()
        head = f"{item['level']} — {name}" if name else str(item["level"])
        return nfc(f"{head} — ngưỡng {item['threshold_xp']} XP")

    # Workshop curriculum entries.
    if "title" in item and "order" in item:
        order = item["order"]
        prefix = f"{order}." if isinstance(order, int) else f"{order}:"
        detail = str(item.get("detail", "")).strip()
        head = f"{prefix} {str(item['title']).strip()}"
        return nfc(f"{head} — {detail}" if detail else head)

    # Operating notes on the master timeline.
    if "detail" in item and "title" in item:
        bits = [f"{str(item['title']).strip()}: {str(item['detail']).strip()}"]
        if item.get("importance"):
            bits.insert(0, f"[{str(item['importance']).strip()}]")
        if item.get("reason"):
            bits.append(f"Lý do: {str(item['reason']).strip()}")
        return nfc(" ".join(bits))

    # Unknown object shape: render every key so nothing is silently dropped.
    return nfc("; ".join(f"{k}: {v}" for k, v in sorted(item.items()) if v not in (None, "", [])))


def render_content(value: Any) -> str:
    if isinstance(value, list):
        lines = [render_item(v) for v in value]
        return "\n".join(ln for ln in lines if ln)
    return render_item(value)


# ----------------------------------------------------------------------- extraction


class Chunk(dict):
    """A chunk record plus the bookkeeping the dedup pass needs."""

    @property
    def tokens(self) -> set[str]:
        if "_tokens" not in self:
            self["_tokens"] = tokens(self["content"])
        return self["_tokens"]


def build_chunk(
    *,
    source_file: str,
    source_path: str,
    pointer: str,
    mtime: str,
    doc: dict,
    title: str,
    content: str,
    section: str | None = None,
    keywords: Iterable[str] = (),
    priority: Any = None,
    status: str = "active",
    week: int | None = None,
    day: str | None = None,
    event_type: str | None = None,
) -> Chunk | None:
    content = nfc(content).strip()
    if not content:
        return None

    doc_meta = doc.get("metadata") or {}
    cohort = doc_meta.get("cohort")
    if priority is None:
        priority = doc_meta.get("priority")

    record = Chunk(
        id=make_id(source_file, pointer),
        source_file=source_file,
        source_type=doc.get("doc_type"),
        title=nfc(str(title).strip()),
        section=nfc(str(section).strip()) if section else None,
        content=content,
        summary=extractive_summary(content),
        keywords=clean_keywords(keywords),
        cohort=nfc(cohort) if isinstance(cohort, str) else None,
        version=SCHEMA_VERSION,
        status=status,
        priority=priority if isinstance(priority, int) else None,
        updated_at=mtime,
        created_at=mtime,
        day=day,
        week=week,
        event_type=nfc(event_type) if event_type else None,
        source_path=source_path,
        source_pointer=pointer,
        language=doc.get("language"),
        source_origin=doc.get("source_type") or doc_meta.get("source"),
        hash=sha256(norm_for_hash(content)),
    )
    return record


def extract_file(path: Path, repo_root: Path) -> tuple[list[Chunk], list[dict]]:
    """Return (chunks, skipped) for one source file."""
    source_file = path.name
    source_path = str(path.relative_to(repo_root))
    mtime = iso_mtime(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc_kw = doc.get("keywords", [])
    section_name = (doc.get("section") or {}).get("name")

    chunks: list[Chunk] = []
    skipped: list[dict] = []

    def add(chunk: Chunk | None, pointer: str) -> None:
        if chunk is None:
            skipped.append(
                {
                    "source_file": source_file,
                    "source_pointer": pointer,
                    "reason": "empty_or_placeholder_content",
                    "detail": "Source unit rendered to empty text; nothing to embed.",
                }
            )
            return
        chunks.append(chunk)

    common = dict(source_file=source_file, source_path=source_path, mtime=mtime, doc=doc)

    # --- shape 1: timeline[] + operating_notes[] + note (master_timeline.json)
    for i, entry in enumerate(doc.get("timeline", [])):
        pointer = f"/timeline/{i}"
        parts = [str(entry.get("milestone", "")).strip()]
        if entry.get("focus"):
            parts.append(str(entry["focus"]).strip())
        if entry.get("gate"):
            parts.append(f"Gate: {entry['gate']}.")
        if entry.get("action"):
            parts.append(str(entry["action"]).strip())
        rng = str(entry.get("range", "")).strip()
        week_no = entry.get("week")
        title = f"Tuần {week_no} ({rng})" if rng else f"Tuần {week_no}"
        raw_status = str(entry.get("status", "")).strip().casefold()
        add(
            build_chunk(
                **common,
                pointer=pointer,
                title=title,
                content="\n".join(p for p in parts if p),
                section=section_name,
                keywords=doc_kw,
                priority=entry.get("priority"),
                status=STATUS_MAP.get(raw_status, "active"),
                week=week_no if isinstance(week_no, int) else None,
            ),
            pointer,
        )

    for i, note in enumerate(doc.get("operating_notes", [])):
        pointer = f"/operating_notes/{i}"
        add(
            build_chunk(
                **common,
                pointer=pointer,
                title=str(note.get("title", "")).strip(),
                content=render_item(note),
                section=section_name,
                keywords=doc_kw,
            ),
            pointer,
        )

    if isinstance(doc.get("note"), str) and doc["note"].strip():
        pointer = "/note"
        add(
            build_chunk(
                **common,
                pointer=pointer,
                title=f"{doc.get('title', source_file)} — lưu ý",
                content=doc["note"],
                section=section_name,
                keywords=doc_kw,
            ),
            pointer,
        )

    # --- shape 2: author-provided chunks[] (cohort3_evening_calendar.json)
    for i, ch in enumerate(doc.get("chunks", [])):
        pointer = f"/chunks/{i}"
        meta = ch.get("metadata") or {}
        add(
            build_chunk(
                **common,
                pointer=pointer,
                title=str(ch.get("title", "")).strip(),
                content=render_content(ch.get("content")),
                section=section_name,
                keywords=clean_keywords(meta.get("tags", []), doc_kw),
                priority=meta.get("priority"),
                event_type=meta.get("event_type"),
            ),
            pointer,
        )

    # --- shape 2b: events[] — extracted alongside chunks[]; the dedup pass decides.
    # They survive as distinct chunks because they answer different granularities
    # ("which activities recur" vs "when exactly is Demo Day") and carry the only
    # event_type/day metadata in the corpus.
    for i, ev in enumerate(doc.get("events", [])):
        pointer = f"/events/{i}"
        pattern = ev.get("date_pattern")
        dates = [d for d in pattern if isinstance(d, str)] if isinstance(pattern, list) else []
        parts = [str(ev.get("description", "")).strip()]
        if dates:
            parts.append("Ngày: " + ", ".join(dates) + ".")
        elif isinstance(pattern, str) and pattern.strip():
            parts.append(f"Tần suất: {pattern.strip()}.")
        add(
            build_chunk(
                **common,
                pointer=pointer,
                title=str(ev.get("event_type", "")).strip(),
                content="\n".join(p for p in parts if p),
                section=section_name,
                keywords=clean_keywords(ev.get("tags", []), doc_kw),
                priority=ev.get("priority"),
                event_type=ev.get("event_type"),
                day=dates[0] if len(dates) == 1 else None,
            ),
            pointer,
        )

    # --- shape 3/4/5: blocks[] or sections[] of a single topic file
    for key in ("blocks", "sections"):
        for i, blk in enumerate(doc.get(key, [])):
            pointer = f"/{key}/{i}"
            meta = blk.get("metadata") or {}
            add(
                build_chunk(
                    **common,
                    pointer=pointer,
                    title=str(blk.get("title", "")).strip(),
                    content=render_content(blk.get("content")),
                    section=section_name,
                    keywords=clean_keywords(meta.get("tags", []), blk.get("keywords", []), doc_kw),
                    priority=meta.get("priority"),
                ),
                pointer,
            )

    # --- shape 6: documents[] -> sections[] (cohort3_knowledge_base.json aggregate)
    for di, sub in enumerate(doc.get("documents", [])):
        sub_title = str(sub.get("title", "")).strip()
        for si, sec in enumerate(sub.get("sections", [])):
            pointer = f"/documents/{di}/sections/{si}"
            raw_status = str(sec.get("status", "")).strip().casefold()
            m = re.search(r"tuần\s+(\d+)", str(sec.get("title", "")), re.IGNORECASE)
            add(
                build_chunk(
                    **common,
                    pointer=pointer,
                    title=str(sec.get("title", "")).strip(),
                    content=render_content(sec.get("content")),
                    section=sub_title,
                    keywords=clean_keywords(sec.get("keywords", []), doc_kw),
                    status=STATUS_MAP.get(raw_status, "active"),
                    week=int(m.group(1)) if m else None,
                ),
                pointer,
            )

    return chunks, skipped


# --------------------------------------------------------------------------- dedup


def rank_key(chunk: Chunk) -> tuple:
    """Lower sorts better. Canonical > high-priority > richer > newer > stable id.

    Canonical outranks recency on purpose: the aggregate knowledge-base file is
    newer than the standalone topic files but is a strictly lossier restatement of
    them (it drops week ranges, gate labels, per-item ordering and detail fields).
    """
    return (
        1 if chunk["source_file"] in AGGREGATE_FILES else 0,
        chunk["priority"] if chunk["priority"] is not None else 99,
        -len(chunk["content"]),
        # newer first, via negated epoch derived from the ISO timestamp
        -int(dt.datetime.fromisoformat(chunk["updated_at"]).timestamp()),
        chunk["id"],
    )


def dedupe(chunks: list[Chunk]) -> tuple[list[Chunk], list[dict]]:
    ordered = sorted(chunks, key=rank_key)
    kept: list[Chunk] = []
    removed: list[dict] = []

    by_hash: dict[str, Chunk] = {}
    for chunk in ordered:
        exact = by_hash.get(chunk["hash"])
        if exact is not None:
            removed.append(
                {
                    "removed_id": chunk["id"],
                    "removed_source": f"{chunk['source_file']}{chunk['source_pointer']}",
                    "kept_id": exact["id"],
                    "kept_source": f"{exact['source_file']}{exact['source_pointer']}",
                    "reason": "duplicate_exact",
                    "similarity": 1.0,
                }
            )
            continue

        near = None
        best = 0.0
        for candidate in kept:
            score = jaccard(chunk.tokens, candidate.tokens)
            if score > best:
                best, near = score, candidate
        if near is not None and best >= NEAR_DUP_THRESHOLD:
            removed.append(
                {
                    "removed_id": chunk["id"],
                    "removed_source": f"{chunk['source_file']}{chunk['source_pointer']}",
                    "kept_id": near["id"],
                    "kept_source": f"{near['source_file']}{near['source_pointer']}",
                    "reason": "duplicate_near",
                    "similarity": round(best, 4),
                }
            )
            continue

        by_hash[chunk["hash"]] = chunk
        kept.append(chunk)

    return kept, removed


def near_miss_report(kept: list[Chunk]) -> list[dict]:
    """Pairs just under the threshold — the audit trail for threshold tuning."""
    out = []
    for i, a in enumerate(kept):
        for b in kept[i + 1 :]:
            score = jaccard(a.tokens, b.tokens)
            if 0.35 <= score < NEAR_DUP_THRESHOLD:
                out.append(
                    {
                        "a": f"{a['source_file']}{a['source_pointer']}",
                        "b": f"{b['source_file']}{b['source_pointer']}",
                        "similarity": round(score, 4),
                        "decision": "kept_both",
                    }
                )
    return sorted(out, key=lambda r: (-r["similarity"], r["a"], r["b"]))


# ---------------------------------------------------------------------------- main

FIELD_ORDER = [
    "id", "source_file", "source_type", "title", "section", "content", "summary",
    "keywords", "cohort", "version", "status", "priority", "updated_at", "created_at",
    "day", "week", "event_type", "source_path", "source_pointer", "language",
    "source_origin", "hash",
]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="codebase/data/rag")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()

    in_dir = (repo_root / args.input).resolve()
    out_dir = (repo_root / args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob("*.json"))
    all_chunks: list[Chunk] = []
    skipped: list[dict] = []
    per_file: dict[str, int] = {}

    for path in files:
        chunks, file_skipped = extract_file(path, repo_root)
        all_chunks.extend(chunks)
        skipped.extend(file_skipped)
        per_file[path.name] = len(chunks)

    # Non-.json files in the input dir are outside the requested glob. Report, never guess.
    ignored = sorted(
        p.name for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() != ".json"
    )

    kept, removed = dedupe(all_chunks)
    kept.sort(key=lambda c: (c["source_file"], c["source_pointer"]))

    chunks_path = out_dir / "rag_chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as fh:
        for chunk in kept:
            record = {k: chunk[k] for k in FIELD_ORDER}
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")

    report = {
        "generated_by": "scripts/build_rag_chunks.py",
        "schema_version": SCHEMA_VERSION,
        "near_dup_threshold": NEAR_DUP_THRESHOLD,
        "input_dir": str(in_dir.relative_to(repo_root)),
        "source_files_scanned": [p.name for p in files],
        "non_json_files_ignored": ignored,
        "totals": {
            "chunks_extracted": len(all_chunks),
            "chunks_kept": len(kept),
            "chunks_removed": len(removed),
            "units_skipped_empty": len(skipped),
        },
        "chunks_extracted_per_file": per_file,
        "kept_per_file": {
            name: sum(1 for c in kept if c["source_file"] == name) for name in per_file
        },
        "removed": sorted(removed, key=lambda r: (r["reason"], r["removed_id"])),
        "skipped_empty_units": skipped,
        "near_misses_below_threshold": near_miss_report(kept),
    }
    (out_dir / "rag_dedup_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"extracted={len(all_chunks)} kept={len(kept)} removed={len(removed)}")
    print(f"wrote {chunks_path.relative_to(repo_root)}")
    for row in report["removed"]:
        print(f"  - {row['reason']} {row['similarity']}: {row['removed_source']} -> {row['kept_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
