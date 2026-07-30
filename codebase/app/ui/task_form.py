"""Trang 'Nhập task': thêm task tay + import deadline mock từ Vlearn."""
from __future__ import annotations

import datetime as dt

import streamlit as st

from app.database import get_session
from app.models import STATUSES, Task
from app.services.vlearn_import import import_vlearn_deadlines


def render() -> None:
    st.header("Nhập task")

    st.subheader("Import deadline từ Vlearn (mock)")
    st.caption(
        "Đọc file mock `data/vlearn_deadlines.json` — mô phỏng đồng bộ deadline, "
        "không gọi API Vlearn thật. Bấm nhiều lần không tạo trùng."
    )
    if st.button("📥 Import từ Vlearn"):
        result = import_vlearn_deadlines()
        if result.get("error"):
            st.error(result["error"])
        else:
            st.success(f"Đã import {result['created']} task mới (bỏ qua {result['skipped']} task đã có).")

    st.divider()

    st.subheader("Thêm task tay")
    with st.form("add_task_form", clear_on_submit=True):
        title = st.text_input("Tên task *")
        description = st.text_area("Mô tả", height=80)

        col1, col2 = st.columns(2)
        with col1:
            due_date_val = st.date_input("Ngày hết hạn *", value=dt.date.today())
            importance = st.slider("Mức quan trọng (1-5)", min_value=1, max_value=5, value=3)
        with col2:
            due_time_val = st.time_input("Giờ hết hạn", value=dt.time(23, 59))
            status = st.selectbox("Trạng thái", STATUSES, index=0)

        assignee = st.text_input("Người phụ trách")

        submitted = st.form_submit_button("Lưu task")
        if submitted:
            if not title.strip():
                st.error("Tên task không được để trống.")
            else:
                due_date = dt.datetime.combine(due_date_val, due_time_val)
                blocked_since = dt.datetime.now() if status == "blocked" else None
                with get_session() as session:
                    task = Task(
                        title=title.strip(),
                        description=description.strip(),
                        due_date=due_date,
                        importance=importance,
                        status=status,
                        assignee=assignee.strip(),
                        source="manual",
                        blocked_since=blocked_since,
                    )
                    session.add(task)
                    session.commit()
                st.success(f"Đã lưu task '{title.strip()}'.")
