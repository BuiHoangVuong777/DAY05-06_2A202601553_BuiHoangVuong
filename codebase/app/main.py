"""StudyPulse — Streamlit entrypoint."""
from __future__ import annotations

import streamlit as st

from app.database import init_db, seed_demo_data
from app.ui import task_form, today_page

st.set_page_config(page_title="StudyPulse", page_icon="📌", layout="wide")

init_db()
seed_demo_data()

PAGES = {
    "Nhập task": task_form.render,
    "Hôm nay": today_page.render,
}

st.sidebar.title("📌 StudyPulse")
st.sidebar.caption("AI nhắc tiến độ học tập cho nhóm sinh viên")
choice = st.sidebar.radio("Điều hướng", list(PAGES.keys()))

PAGES[choice]()
