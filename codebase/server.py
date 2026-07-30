from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="AI Study Progress Assistant",
    version="1.0.0",
)


class StrategyRequest(BaseModel):
    task_title: str = Field(min_length=1)
    deadline: str | None = None
    importance: str = "medium"
    status: str = "not_started"
    blocker: str | None = None


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/strategy")
def create_strategy(request: StrategyRequest) -> dict:
    try:
        # Sau này thay phần mock này bằng:
        # from app.services.ai_service import generate_strategy
        # return generate_strategy(request.model_dump())

        priority_reason = "Task có mức ưu tiên thông thường."

        if request.blocker:
            priority_reason = (
                f"Cần xử lý blocker '{request.blocker}' trước "
                "vì nó đang cản trở tiến độ."
            )
        elif request.importance == "high":
            priority_reason = "Task có mức độ quan trọng cao."

        return {
            "task": request.task_title,
            "priority": "high" if request.blocker else request.importance,
            "reason": priority_reason,
            "steps": [
                "Kiểm tra trạng thái và thông tin task.",
                "Xử lý blocker trước khi thêm tính năng mới.",
                "Cập nhật tiến độ sau khi hoàn thành.",
            ],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Không thể tạo chiến lược.",
        ) from exc


# Đặt sau các API route để /api/... được xử lý trước.
app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)