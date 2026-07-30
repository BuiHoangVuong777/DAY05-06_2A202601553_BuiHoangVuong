"""Load environment variables and shared constants for StudyPulse."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
CODEBASE_DIR = APP_DIR.parent
DATA_DIR = CODEBASE_DIR / "data"
PROMPTS_DIR = APP_DIR / "prompts"

load_dotenv(CODEBASE_DIR / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

DATABASE_PATH = DATA_DIR / "studypulse.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

VLEARN_MOCK_PATH = DATA_DIR / "vlearn_deadlines.json"

# Sau bao nhiêu ngày blocked liên tục thì gắn cờ "kẹt lâu".
BLOCKED_DAYS_THRESHOLD = 2

# Trong vòng bao nhiêu ngày tới thì tính là "sắp đến hạn" (ưu tiên cao hơn).
DUE_SOON_DAYS = 3

# Một mục tiêu tuần bị coi là "thiếu tiến độ" nếu không có task nào
# done/doing được cập nhật trong N ngày gần đây trong khi còn task todo/blocked.
WEEKLY_STALL_DAYS = 3
