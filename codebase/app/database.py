"""Engine/session setup + seed data for StudyPulse."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATA_DIR, DATABASE_URL
from app.models import Base, Task

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()


def seed_demo_data() -> None:
    """Chèn vài task thêm tay mẫu nếu DB đang trống, để demo không bị trơ ngay lần đầu."""
    with get_session() as session:
        has_any = session.execute(select(Task.id).limit(1)).first()
        if has_any:
            return

        now = dt.datetime.now()
        demo_tasks = [
            Task(
                title="Chuẩn bị slide demo nhóm",
                description="Gom kết quả các phần, dựng 6 trang slide theo mẫu.",
                due_date=now + dt.timedelta(days=1, hours=2),
                importance=5,
                status="doing",
                assignee="Vương",
                source="manual",
            ),
            Task(
                title="Viết báo cáo evidence khảo sát",
                description="Tổng hợp 20 câu trả lời khảo sát pain.",
                due_date=now - dt.timedelta(hours=5),
                importance=4,
                status="blocked",
                assignee="Lan",
                source="manual",
                blocked_since=now - dt.timedelta(days=3),
            ),
            Task(
                title="Review code rule engine",
                description="Đọc lại logic chấm điểm ưu tiên trước khi demo.",
                due_date=now + dt.timedelta(days=4),
                importance=2,
                status="todo",
                assignee="Minh",
                source="manual",
            ),
        ]
        session.add_all(demo_tasks)
        session.commit()
