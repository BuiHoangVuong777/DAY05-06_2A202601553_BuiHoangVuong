"""Trang 'Hôm nay': danh sách task sắp theo priority_score (rule engine), có cờ cảnh báo."""
from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from app.database import get_session
from app.models import Task
from app.services.priority_engine import rank_tasks

STATUS_LABEL = {
    "todo": "Chưa làm",
    "doing": "Đang làm",
    "blocked": "Đang kẹt",
    "done": "Xong",
}


def _load_ranked_tasks() -> list[Task]:
    with get_session() as session:
        tasks = session.execute(select(Task)).scalars().all()
        ranked = rank_tasks(tasks)
        session.commit()  # lưu priority_score/priority_reason vừa tính
        return ranked


def render() -> None:
    st.header("Hôm nay")
    st.caption("Sắp xếp theo điểm ưu tiên do rule engine chấm — không dùng AI, deterministic.")

    tasks = _load_ranked_tasks()

    if not tasks:
        st.info("Chưa có task nào. Vào trang 'Nhập task' để thêm hoặc import từ Vlearn.")
        return

    for task in tasks:
        flags = getattr(task, "flags", {})
        badges = []
        if flags.get("overdue"):
            badges.append("🔴 Quá hạn")
        if flags.get("due_soon"):
            badges.append("⏰ Sắp đến hạn")
        if flags.get("blocked_long"):
            badges.append("🚧 Kẹt lâu")
        if task.status == "done":
            badges.append("✅ Xong")

        with st.container(border=True):
            top = st.columns([5, 2])
            top[0].markdown(f"**{task.title}**")
            top[1].markdown(" ".join(badges) if badges else "")

            cols = st.columns(4)
            cols[0].caption(f"Hạn: {task.due_date:%d/%m %H:%M}")
            cols[1].caption(f"Trạng thái: {STATUS_LABEL.get(task.status, task.status)}")
            cols[2].caption(f"Quan trọng: {task.importance}/5")
            cols[3].caption(f"Phụ trách: {task.assignee or '(chưa gán)'}")

            if task.description:
                st.caption(task.description)

            st.caption(f"🧮 Điểm ưu tiên: {task.priority_score:.0f} — {task.priority_reason}")
            st.caption(f"Nguồn: {'Vlearn' if task.source == 'vlearn' else 'Thêm tay'}")
