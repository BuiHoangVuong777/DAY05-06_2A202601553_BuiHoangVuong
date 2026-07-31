# RAG app — Chroma + FastAPI + static frontend

Dockerized RAG over the chunks produced by [`scripts/build_rag_chunks.py`](../scripts/build_rag_chunks.py).

```
┌──────────┐   /api/*   ┌─────────┐  embed+query  ┌────────┐
│ frontend │ ─────────▶ │ backend │ ────────────▶ │ chroma │
│  nginx   │   proxy    │ FastAPI │               │ +volume│
└──────────┘            └────┬────┘               └────────┘
   :3000                     │ OpenAI (optional)
                             ▼
                     answer + sources
```

## Run it

```bash
cd rag-app
cp .env.example .env      # optional: paste OPENAI_API_KEY into .env
docker compose up --build
```

Open **<http://localhost:3000>**. That's the whole setup.

The first build takes a few minutes — it installs CPU-only PyTorch and bakes the
embedding model into the image so the container needs **no network at run time**.
Later builds are cached and start in seconds.

**Without an API key it still works.** Retrieval runs, and answers come back
labelled `mode: "fallback"` with the matching chunks — never presented as AI output.
Add the key and restart (`docker compose up -d`) to get generated answers.

## Verify

```bash
curl -s localhost:8000/api/health | python3 -m json.tool

curl -s localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Demo Day diễn ra ngày nào?"}' | python3 -m json.tool
```

`/api/health` reports `chunks_indexed`, `ai_configured`, and the active models.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Chroma connectivity, indexed chunk count, whether AI is configured |
| `POST` | `/api/ingest` | Re-ingest `output/rag_chunks.jsonl`. Idempotent; safe to call anytime |
| `POST` | `/api/query` | `{question, top_k?}` → `{answer, mode, warning, model, sources[]}` |
| `POST` | `/api/chat` | Alias for `/api/query` |

## How ingestion works

`../output` is mounted **read-only** at `/data`, so regenerating chunks needs no rebuild:

```bash
python3 ../scripts/build_rag_chunks.py     # regenerate chunks
curl -X POST localhost:8000/api/ingest     # re-index
```

Chunks upsert by their stable `id` and are **skipped when the content `hash` is
unchanged**, so restarts and re-runs cost nothing. Embedded text is
`title + section + content` — the titles carry retrieval signal the body lacks.
Set `AUTO_INGEST=false` to skip the startup ingest.

## Configuration

Everything is environment-driven; see [`.env.example`](.env.example). The values
worth knowing:

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | *(empty)* | Empty ⇒ fallback mode, no crash |
| `OPENAI_BASE_URL` | *(empty)* | Set for Azure / OpenRouter / vLLM / any OpenAI-compatible gateway |
| `OPENAI_MODEL_1` | `gpt-4o-mini` | Primary model |
| `OPENAI_MODEL_2` | *(empty)* | Secondary, tried only if `MODEL_1` errors or returns nothing |
| `OPENAI_MAX_TOKENS` | `1024` | Answer length cap |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | **Must be multilingual** — the corpus is Vietnamese |
| `TOP_K` | `5` | Chunks retrieved per question |
| `FRONTEND_PORT` | `3000` | |
| `BACKEND_URL` | `http://backend:8000` | Where nginx proxies `/api` |

The frontend calls `/api/*` on its own origin and nginx proxies to `BACKEND_URL`
— so there is no CORS configuration and no API URL baked into the page.

### Changing the embedding model

The model is baked into the image, so a model change needs a rebuild — an `.env`
edit alone is not enough:

```bash
docker compose up -d --build
```

You do **not** need to wipe the volume. Each chunk stores the model that embedded
it, and ingestion re-embeds any chunk whose model no longer matches, so the
collection heals itself on the next startup. (Without that check, switching models
would look like a no-op — the content hashes still match, both models are 384-dim
so nothing errors, and queries would be matched against vectors from the old model.
Silently wrong results, which is the worst kind.)

**Avoid the e5 family** (`intfloat/multilingual-e5-*`). Those models are trained
with `"query: "` / `"passage: "` prefixes, but Chroma applies a single embedding
function to documents and queries alike — the prefixes can't be set
asymmetrically, so retrieval quality drops with no error to tell you. The default
is symmetric and needs no prefixes. If you do want e5, embed manually instead of
letting Chroma do it.

## Data & persistence

Chroma writes to the named volume `chroma-data` (`/data` inside the container), so
the index survives `docker compose restart` and `down`. Only `docker compose down -v`
erases it.

Chroma is published on `localhost:8001` and the backend on `localhost:8000` for
debugging. Neither is needed in normal use — **drop both `ports:` blocks before
exposing this to a network**; nothing here has authentication.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `chunks_indexed: 0` | `output/rag_chunks.jsonl` missing. Run `python3 ../scripts/build_rag_chunks.py`, then `POST /api/ingest` |
| Backend restarts at boot | It retries Chroma for ~60s; check `docker compose logs chroma` |
| Answers always `mode: "fallback"` | No `OPENAI_API_KEY` in `.env`, or every configured model failed — the `warning` field names each one |
| Slow answer when `MODEL_1` is down | The SDK retries each model internally before moving on, so failover costs a few attempts × `OPENAI_TIMEOUT`. Lower `OPENAI_TIMEOUT` for a snappier demo |
| Irrelevant Vietnamese results | `EMBEDDING_MODEL` was changed to an English-only or e5-family model (see above) |
| Model change seems ignored | The model is baked in — use `docker compose up -d --build`, not just an `.env` edit |
| Port already in use | Change `FRONTEND_PORT` / `BACKEND_PUBLIC_PORT` / `CHROMA_PUBLIC_PORT` in `.env` |

## Deliberately not included

No Redis, Postgres, Celery, auth, or observability stack — three containers, one
command. Reranking, streaming responses, and conversation history are the obvious
next additions if the demo needs them.
