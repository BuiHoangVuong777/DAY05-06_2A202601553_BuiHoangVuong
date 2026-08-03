# Agent context — StudyFlow / NotHackathon (Batch 03 Mini Hackathon)

> Grounded in repo content as of commit `46153f1` (2026-07-30). Uncertain items are marked **[unverified]**.

## 1. Project summary

- Hackathon **submission repo**, not a product repo. Graded artifact = `spec.md` + working prototype + demo, against `04-rubric.md` (100 pts: 25 checkpoint + 75 artifact).
- Team `NotHackathon`, Zone 3, Track C. All docs/UI/comments are **Vietnamese** — match that language when editing.
- Product slice (one sentence, from [spec.md](spec.md) §4): student types a study update in one sentence → AI drafts a structured task → user confirms → deterministic rule engine ranks what to do first → team sees a Discord reminder **preview**.
- Declared prototype level: **Mock**. Real: SQLite, rule engine, UI. Mock: VLearn sync, Discord send. AI: real only in the legacy tree, with a labelled fallback.
- Root `README.md` doubles as the original event brief (files `01-`…`04-` are instructor material — **do not edit them**).

## 2. Architecture — three parallel, non-integrated implementations

This is the single most important fact. There is no unified app; three stacks coexist and do **not** talk to each other.

| # | Tree | Stack | Has AI? | Has DB? | Serves UI? |
|---|---|---|---|---|---|
| A | [codebase/server.py](codebase/server.py) | FastAPI, 70 lines | No — hardcoded dict | No | Yes, mounts `frontend/` |
| B | [codebase/app/](codebase/app/) | Streamlit + SQLAlchemy/SQLite | No | Yes (`data/studypulse.db`) | Own Streamlit pages |
| C | [codebase_legacy_studyflow/](codebase_legacy_studyflow/) | stdlib `http.server` + sqlite3 | **Yes (Gemini)** | Yes (`data/studyflow.db`) | Broken — see below |

- **A** exposes exactly two routes: `GET /api/health` → `{"status":"ok"}`, `POST /api/strategy` → a canned dict. Static mount is registered **after** the API routes on purpose ([server.py:66-71](codebase/server.py#L66-L71)).
- **B** is a completely separate program (`streamlit run app/main.py`). It shares `codebase/` only as a directory. Naming drifted: internally it calls itself **StudyPulse**.
- **C** is the only place the spec'd flow actually exists end-to-end. It is the origin of the API contract that `frontend/public/app.js` still expects. Its `PUBLIC_DIR` (`codebase_legacy_studyflow/public/`) **does not exist**, so `GET /` 404s; the JSON API still works.

### Frontend (`codebase/frontend/`) — what is live vs dead

| File | Status |
|---|---|
| [index.html](codebase/frontend/index.html) (886 L) | **Live.** React 18 UMD + Babel-standalone + Tailwind, all from CDN. **100% hardcoded mock state** (`initialWeeks`, `initialNotifications` in `useState`). Makes **no** backend calls. Links to `/strategy.html` at L784. |
| [strategy.html](codebase/frontend/strategy.html) (568 L) | **Live.** Tailwind CDN + a 400-line **inline** `<script>` (L171-566). Only page that calls the backend (`POST /api/strategy`, L486). |
| [public/strategy.js](codebase/frontend/public/strategy.js) | **Dead.** Not referenced by any HTML. A *stale, divergent* copy of strategy.html's inline script (different state shape: no `state.strategy`, no `.title`/`.deadline`). Editing it changes nothing. |
| [public/app.js](codebase/frontend/public/app.js) | **Dead.** Not referenced. Written against tree **C**'s API (`/api/dashboard`, `/api/ai/parse-task`, `/api/tasks`, `/api/tasks/:id/check-in`, `health.ai_configured`). Best surviving spec of the intended UI. |
| [styles.css](codebase/frontend/styles.css) (834 L) | **Dead.** Not referenced by either HTML page (both use Tailwind CDN). |

## 3. input → AI → validation → UI flow

Fully implemented **only in tree C** ([ai_service.py](codebase_legacy_studyflow/studyflow/ai_service.py)):

1. **Input** — `POST /api/ai/parse-task {text}`. Guards: non-empty, ≤ 2 000 chars, else `ValueError` → HTTP 400.
2. **Gate** — if `api_key` empty → skip network entirely, return `mode:"fallback"` immediately.
3. **AI call** — single-shot Vietnamese prompt + JSON schema to Gemini Interactions API, `store:false`, `thinking_level:"low"`, `max_output_tokens:700`, 20 s timeout.
4. **Extraction** — `_extract_output_text` walks `response["steps"][]` for `type=="model_output"` then `content[].type=="text"`; raises if no text chunk.
5. **Validation** — `_validate` (see §5). Any failure raises `ValueError`.
6. **Fallback** — the `try` catches `URLError | TimeoutError | JSONDecodeError | ValueError`, so *both* network failures and schema violations degrade to the rule fallback, never to an error page.
7. **Trace** — every attempt (success or failure) appends one JSONL line to `eval/traces/ai_calls.jsonl` (dir does not exist yet; created on first call).
8. **UI** — response is `{mode, model, warning, task}`. `app.js:setDraft` pre-fills an **editable** form; `mode:"ai"` shows a confidence banner, anything else shows the `warning` text and a non-AI banner. Nothing is saved until the user submits `POST /api/tasks`.
9. **Ranking** — after save, `/api/dashboard` re-runs the deterministic rule engine; every card shows score + reasons.

In tree A the "AI" step is a branch on `request.blocker` / `request.importance` returning fixed Vietnamese strings — but `strategy.html` presents it to the user as *"Đề xuất từ AI"* / *"Đang gọi AI..."*. **This mislabels a hardcoded response as AI output**, which directly contradicts spec §6 ("failure path must not present fallback as AI output"). Fix before demo.

## 4. Key files

- [codebase/server.py](codebase/server.py) — FastAPI app; `StrategyRequest` pydantic model; canned `/api/strategy`; static mount.
- [codebase/app/config.py](codebase/app/config.py) — env + tunables: `BLOCKED_DAYS_THRESHOLD=2`, `DUE_SOON_DAYS=3`, `WEEKLY_STALL_DAYS=3` (last one is **unused**).
- [codebase/app/models.py](codebase/app/models.py) — single `Task` table. `STATUSES=("todo","doing","blocked","done")`, importance is `int`.
- [codebase/app/database.py](codebase/app/database.py) — engine, `init_db`, `seed_demo_data` (3 tasks, only if table empty).
- [codebase/app/services/priority_engine.py](codebase/app/services/priority_engine.py) — rule engine B. Pure, no LLM/DB/network — the easiest thing to unit-test.
- [codebase/app/services/reminder_service.py](codebase/app/services/reminder_service.py) — pure: tasks + now → `{due_today, blocked_alerts}`.
- [codebase/app/services/vlearn_import.py](codebase/app/services/vlearn_import.py) — reads `data/vlearn_deadlines.json`, idempotent by `title` among `source=='vlearn'`.
- [codebase/data/vlearn_deadlines.json](codebase/data/vlearn_deadlines.json) — 8 mock deadlines using **relative** `due_offset_hours` so demos always have overdue + upcoming items regardless of run date.
- [codebase_legacy_studyflow/studyflow/ai_service.py](codebase_legacy_studyflow/studyflow/ai_service.py) — prompt, schema, validation, fallback, tracing.
- [codebase_legacy_studyflow/studyflow/rule_engine.py](codebase_legacy_studyflow/studyflow/rule_engine.py) — rule engine C + `build_dashboard` (KPIs, `discord_preview` with `is_mock:true`).
- [codebase_legacy_studyflow/studyflow/repository.py](codebase_legacy_studyflow/studyflow/repository.py) — sqlite3 `tasks` + `checkins`, whitelist validation (`TASK_FIELDS`, `VALID_STATUS`, `VALID_IMPORTANCE`).
- [spec.md](spec.md) — the graded deliverable. §5 error taxonomy and §6 four paths are the behavioural contract.
- [eval/golden-set.json](eval/golden-set.json) — 5 cases, all `review_status:"draft"`.

## 5. Prompt pipeline / schema / fallback (tree C)

**Prompt** ([ai_service.py:157-162](codebase_legacy_studyflow/studyflow/ai_service.py#L157-L162)) — Vietnamese, four instructions: don't invent course/assignee/deadline; resolve relative dates against a supplied UTC `now`; on missing facts emit empty string + lower confidence + exactly one clarifying question; then current UTC time and the raw input.

**Schema** — `additionalProperties:false`, all 9 fields required: `title`, `description`, `course`, `assignee`, `due_at` (`["string","null"]`, date-time), `importance` (enum `low|medium|high`), `confidence` (int 0-100), `ambiguity`, `clarification_question`.

**Post-validation constraints** (`_validate`) — these are the real guarantees, applied on top of the schema:
- `title` stripped, truncated to 180 chars; empty → raise → fallback.
- `importance` not in the enum → silently coerced to `"medium"`.
- `due_at` parsed ISO (`Z`→`+00:00`), naive → assumed UTC, normalized to UTC; empty → **`now + 3 days`** (a silent invention — tension with spec §5 case 2).
- `confidence` clamped to 0-100.

**Fallback** (`_fallback`, keyword rules, `confidence: 35`) — `"hôm nay"` → today 16:59; `"ngày mai"`/`"mai "` → tomorrow 16:59; else `now + 3 days`. `"gấp"|"quan trọng"|"urgent"` → `high`, else `medium`. Title = text up to first `[,.;\n]`, ≤180 chars. Always sets an `ambiguity` + `clarification_question`.

**Tracing** — `trace_full_input=False` by default: only `sha256(input)` is logged, plus timestamp, model, latency, success, output/error, usage.

**[unverified]** The Gemini endpoint shape (`/v1beta/interactions`, `steps[].content[]`, `response_format.schema`, `thinking_level`) and default model `gemini-3.6-flash` were not validated against live Google docs. If AI calls fail with 4xx, suspect this first, not the app logic.

## 6. Two incompatible rule engines

| | `app/services/priority_engine.py` (B) | `studyflow/rule_engine.py` (C) |
|---|---|---|
| statuses | `todo/doing/blocked/done` | `todo/in_progress/blocked/done` |
| importance | `int 1-5` | `"low"/"medium"/"high"` |
| time | **naive local** `datetime.now()` | **tz-aware UTC** |
| done | score `-1000` | score `-1` |
| overdue | `+1000 + min(hours, 500)` | `+100 + min(days*5, 30)` |
| blocked | `+50` if ≥2 days | `+20 + min(days*10, 40)` |
| output | mutates task, sets `.flags` dict | returns `{score, level, reasons, recommendation}` |

Do not copy scoring constants between them; the units differ (hours vs days, int vs string importance).

## 7. Known bugs and risks

**Must fix**
1. **Live-looking OpenAI API key in [codebase/.env.example:4](codebase/.env.example#L4)** — working-tree modification, **not yet committed** (`git log -S` finds nothing; `HEAD` version is clean). `.gitignore` has `*.env`, which does **not** match `.env.example`, so a `git add -A` publishes it. Rotate the key and delete the line before any commit. Nothing in the repo reads `OPENAI_API_KEY`.
2. **`python3 server.py` — the command in both READMEs — silently does nothing.** No `if __name__ == "__main__"`, no `uvicorn.run`. Exits 0 instantly. Use `uvicorn server:app`.
3. `codebase/README.md` is linked from the root README but **does not exist**.
4. Real personal emails and names are in [evidence/survey-log.md](evidence/survey-log.md), against the repo's own anonymization rule (commits `e604c90`, `21ba1c8`). Mask before submission.

**Correctness / dead code**
5. `strategy.js` renders API output into `innerHTML` **unescaped** ([strategy.js:446](codebase/frontend/public/strategy.js#L446)); `app.js` escapes properly. Currently unreachable (dead file) but do not revive as-is.
6. `server.py` `/api/strategy` wraps pure dict construction in `try/except` — the 500 branch is unreachable.
7. `app/config.py` `PROMPTS_DIR` → `app/prompts/`, which does not exist.
8. `requirements.txt` lists `anthropic`; nothing imports it. `config.py` reads `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `DISCORD_WEBHOOK_URL`; nothing consumes them. `.env.example` documents Anthropic + Discord behaviour that is **not implemented anywhere**.
9. `Task.created_at` uses deprecated `dt.datetime.utcnow` ([models.py:33](codebase/app/models.py#L33)).
10. `today_page._load_ranked_tasks` writes `priority_score`/`priority_reason` to SQLite on **every page render** ([today_page.py:23](codebase/app/ui/today_page.py#L23)); `task.flags` is a non-persisted runtime attribute the UI reads via `getattr(task, "flags", {})`.
11. Tree C's `/` returns 404 — `public/` was removed.
12. `requirements.txt` omits `fastapi` and `uvicorn`, which `server.py` needs.
16. **Tree B crashes on launch without `PYTHONPATH=.`** Streamlit inserts the *script's* dir (`codebase/app`) into `sys.path` ([bootstrap.py:70](codebase/venv/lib/python3.12/site-packages/streamlit/web/bootstrap.py#L70)), not `codebase/`, so `from app.database import …` raises `ModuleNotFoundError: No module named 'app'`. Verified both directions. Permanent fix: add a `codebase/streamlit_app.py` shim at the top level, or make the intra-package imports relative.

**Submission gaps (rubric-relevant, not code)**
13. `eval/golden-set.json` has 5 cases; spec §7 and `TEAM-NEXT-STEPS.md` require **≥20, with ≥10 from real evidence/chatlog**. All are `review_status:"draft"`. `eval/traces/` does not exist.
14. `validation/feedback-log.md` table is empty (needs ≥5 outside testers).
15. `spec.md` §3 (competitor research) and the §7 quality bar are still `[CẦN TEAM ĐIỀN]` placeholders.

## 8. Local run / test

```bash
# A — FastAPI + the live HTML frontend (index.html, strategy.html)
cd codebase
./venv/bin/uvicorn server:app --reload --port 8000   # NOT `python3 server.py`
# → http://127.0.0.1:8000/  and  /strategy.html

# B — Streamlit app (separate program, separate DB)
cd codebase
PYTHONPATH=. ./venv/bin/streamlit run app/main.py     # PYTHONPATH=. is REQUIRED, see risk #16

# C — legacy full-flow prototype (only tree with AI); API works, `/` 404s
cd codebase_legacy_studyflow
make run        # python3 server.py — this one DOES have an entrypoint
make test       # python3 -m unittest discover -s tests  → 11 tests, verified passing

# Real AI in tree C
echo 'GEMINI_API_KEY=...' >> codebase_legacy_studyflow/.env   # then restart
```

- `codebase/venv/` is a committed-path-but-gitignored Python 3.12 venv with fastapi 0.141.1, streamlit, SQLAlchemy 2.0.51, pytest 9.1.1. Use `./venv/bin/…`.
- Trees B and C have **separate SQLite files** (`studypulse.db` vs `studyflow.db`); both are gitignored. Deleting either just re-seeds.
- Tree C accepts `?now=<ISO-8601>` on `/api/tasks` and `/api/dashboard` to reproduce time-dependent demo cases deterministically. Use this for testing instead of freezing the clock.
- There are **no tests for trees A or B**. The 11 passing tests only cover tree C.

## 9. Invariants — do not break

1. **Augment, never automate.** AI output is a *draft*; every field stays user-editable and nothing persists without an explicit confirm action (spec §4, HAX G9).
2. **Never present a fallback as AI output.** `mode` must reach the UI; fallback renders a warning banner, not a confidence badge (spec §6). Tree A currently violates this.
3. **Do not invent `assignee`, `course`, or `deadline`.** Missing → empty string + lowered confidence + one clarifying question. This is the golden set's hardest assertion.
4. **The rule engine stays deterministic and LLM-free.** Every ranking must be explainable by `reasons`/`priority_reason` shown in the UI (HAX G11). Never route prioritisation through an LLM.
5. **VLearn and Discord stay mocked.** No writes to VLearn, no real Discord send; `discord_preview.is_mock` must remain `true` and the MOCK label visible.
6. **Never commit** `.env`, API keys, `venv/`, `*.db`, or the raw data pack. Trace files log `sha256(input)` unless `AI_TRACE_FULL_INPUT=true` — keep that default.
7. **Never delete a failing golden-set case or eval run** (`eval/README.md`).
8. `data/vlearn_deadlines.json` must keep **relative** `due_offset_hours`, never absolute dates, or demos break on later dates.
9. Static mount in `server.py` must stay **after** all `/api/…` routes.
10. Instructor files `01-de-bai.md`, `02-guide.md`, `03-template-ai-spec.md`, `04-rubric.md` are read-only reference.

## 10. Operating context for a future agent

- **Ask which tree before editing.** "Fix the priority engine" is ambiguous — B and C both have one, with different units. Default assumption: the demo runs tree **A + `frontend/`**, so user-visible fixes usually belong there.
- **`frontend/public/*.js` and `styles.css` are dead.** Editing them produces no visible change. `strategy.html`'s behaviour lives in its own inline `<script>`.
- **`index.html` is pure mock state.** Any request to "make the dashboard show real data" means wiring it to an API that does not exist yet in tree A — port the contract from `public/app.js` + tree C, don't invent one.
- **The highest-value work is submission gaps, not code**: golden set → 20 cases, validation log → 5 testers, spec §3/§7 placeholders. Rubric weights these.
- **When touching AI behaviour**, tree C is the reference implementation; keep the schema/`_validate`/`_fallback`/trace quartet intact — the spec's transparency claims depend on all four.
- **Language:** Vietnamese for all user-facing strings, comments, and docs.
- **Git hygiene** (`TEAM-NEXT-STEPS.md`): branch `feat/<short-name>`, stage only your own files, and the named author must be able to explain the change at CP5/CP6. Don't commit on `main` without being asked.
