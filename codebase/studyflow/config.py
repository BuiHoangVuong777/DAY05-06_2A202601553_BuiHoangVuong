"""Application configuration with a dependency-free .env loader."""

from __future__ import annotations

import os
from pathlib import Path


CODEBASE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = CODEBASE_DIR.parent


def load_env(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs without overwriting real environment values."""
    env_path = path or CODEBASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


load_env()

HOST = os.getenv("APP_HOST", "127.0.0.1")
PORT = int(os.getenv("APP_PORT", "8000"))
DB_PATH = Path(os.getenv("APP_DB_PATH", str(CODEBASE_DIR / "data" / "studyflow.db")))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
AI_TRACE_PATH = Path(
    os.getenv("AI_TRACE_PATH", str(REPO_DIR / "eval" / "traces" / "ai_calls.jsonl"))
)
AI_TRACE_FULL_INPUT = os.getenv("AI_TRACE_FULL_INPUT", "false").lower() == "true"
