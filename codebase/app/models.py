"""SQLAlchemy model for StudyPulse tasks."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


STATUSES = ("todo", "doing", "blocked", "done")
SOURCES = ("vlearn", "manual")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    due_date: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)
    assignee: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    blocked_since: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    priority_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "importance": self.importance,
            "status": self.status,
            "assignee": self.assignee,
            "source": self.source,
            "blocked_since": self.blocked_since.isoformat() if self.blocked_since else None,
            "priority_score": self.priority_score,
            "priority_reason": self.priority_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
