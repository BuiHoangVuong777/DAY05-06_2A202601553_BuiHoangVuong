"""Xây dữ liệu dashboard THẬT cho index.html từ nguồn có sẵn trong repo.

Tách riêng khỏi server.py vì đây là lớp ánh xạ schema giữa agent/SSOT và UI —
phần dễ phải sửa nhất khi UI đổi. server.py giữ vai trò định tuyến.

Nguồn dữ liệu (không có gì bịa ra):
  - Lộ trình 6 tuần : codebase/data/rag/master_timeline.json  (timeline[])
  - Task / deadline : agent.agent.run()  -> đọc SSOT ssot/ssot.db
  - Lịch sự kiện    : bảng schedules trong SSOT (qua agent.tools)

Trả về đúng schema mà index.html đang dùng:
  weeks[]         {id, week, date, title, subtitle?, status, milestone, progress?, desc, tasks[]}
  notifications[] {id, source, type, title, time, status, progress?, blocker?, details}
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import secrets
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent          # codebase/
REPO_ROOT = BASE_DIR.parent                          # gốc repo
TIMELINE_PATH = BASE_DIR / "data" / "rag" / "master_timeline.json"
USERS_SEED_PATH = BASE_DIR / "users_seed.json"

log = logging.getLogger("vlearn.dashboard")

# agent/ nằm ở gốc repo, không phải trong codebase/ -> thêm vào sys.path.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from agent import agent as agent_core, tools as agent_tools
    AGENT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001 - thiếu agent thì báo rõ, không sập server
    agent_core = agent_tools = None  # type: ignore[assignment]
    AGENT_ERROR = f"{type(exc).__name__}: {exc}"
    log.warning("Không import được agent: %s", AGENT_ERROR)

# ------------------------------------------------------------------ tài khoản
_seed_cache: dict[str, Any] | None = None


def _doc_seed() -> dict[str, Any]:
    """Đọc users_seed.json (cache lại). Thiếu file thì trả rỗng, không ném lỗi."""
    global _seed_cache
    if _seed_cache is None:
        try:
            _seed_cache = json.loads(USERS_SEED_PATH.read_text(encoding="utf-8"))
        except OSError as exc:
            log.warning("Không đọc được %s: %s", USERS_SEED_PATH, exc)
            _seed_cache = {"users": []}
    return _seed_cache


def lay_ho_so(username: str | None) -> dict[str, Any] | None:
    """Hồ sơ công khai của một tài khoản (không kèm mật khẩu/hash)."""
    if not username:
        return None
    for u in _doc_seed().get("users", []):
        if u.get("username") == username:
            return {k: v for k, v in u.items()
                    if k not in ("password_sha256", "password_dev_plaintext")}
    return None


def xac_thuc(username: str, password: str) -> dict[str, Any] | None:
    """Kiểm tra cặp tài khoản/mật khẩu theo seed. Mỗi người một mật khẩu riêng.

    So sánh sha256 bằng compare_digest để tránh rò rỉ thời gian. Hash không salt
    — đủ cho demo, KHÔNG dùng cho production.
    """
    bam = hashlib.sha256(password.encode()).hexdigest()
    for u in _doc_seed().get("users", []):
        if secrets.compare_digest(u.get("username", ""), username) and \
           secrets.compare_digest(u.get("password_sha256", ""), bam):
            return {k: v for k, v in u.items()
                    if k not in ("password_sha256", "password_dev_plaintext")}
    return None


# Trạng thái trong master_timeline.json -> trạng thái UI.
TRANG_THAI_TUAN = {"đã xong": "completed", "hiện tại": "current", "upcoming": "upcoming"}


def _nam_moc() -> int:
    """Lấy năm từ chính file timeline (vd '01/09/2026'), không hardcode."""
    try:
        raw = TIMELINE_PATH.read_text(encoding="utf-8")
        nam = re.findall(r"/(\d{4})\b", raw)
        return int(nam[0]) if nam else dt.date.today().year
    except OSError:
        return dt.date.today().year


def _khoang_ngay(pham_vi: str, nam: int) -> tuple[dt.date | None, dt.date | None]:
    """'23/07 - 29/07' -> (date, date). '01/09/2026' -> (date, date) cùng ngày."""
    moc = re.findall(r"(\d{2})/(\d{2})(?:/(\d{4}))?", pham_vi or "")
    if not moc:
        return None, None
    def _d(m):
        d, thang, y = m
        return dt.date(int(y) if y else nam, int(thang), int(d))
    dau = _d(moc[0])
    cuoi = _d(moc[1]) if len(moc) > 1 else dau
    return dau, cuoi


def _gio_viet(iso: str | None) -> str:
    """ISO -> chuỗi giờ tiếng Việt. Không có hạn thì nói rõ là chưa xác định."""
    if not iso:
        return "Chưa xác định"
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", ""))
    except ValueError:
        return str(iso)
    hom_nay = dt.datetime.utcnow().date()
    gio = d.strftime("%H:%M")
    if d.date() == hom_nay:
        return f"{gio} hôm nay"
    if d.date() == hom_nay + dt.timedelta(days=1):
        return f"{gio} ngày mai"
    if d.date() < hom_nay:
        return f"{gio} {d.strftime('%d/%m')} (đã qua hạn)"
    return f"{gio} {d.strftime('%d/%m')}"


def _trang_thai_thong_bao(muc: dict, nhom: str) -> str:
    """Ánh xạ sang đúng tập trạng thái UI: todo | blocked | upcoming | needs_confirmation."""
    if not muc.get("deadline"):
        # Giữ đúng ngữ nghĩa mock cũ: thiếu hạn thì chờ xác nhận, không tự đoán.
        return "needs_confirmation"
    if muc.get("status") == "blocked":
        return "blocked"
    return "upcoming" if nhom == "due_soon" else "todo"


def _thong_bao_tu_task(muc: dict, nhom: str) -> dict[str, Any]:
    tt = _trang_thai_thong_bao(muc, nhom)
    ra: dict[str, Any] = {
        "id": f"task-{muc.get('task_id')}",
        "source": "VLearn",
        "type": muc.get("project_id") or "Task",
        "title": muc.get("title") or "(không có tiêu đề)",
        "time": _gio_viet(muc.get("deadline")),
        "status": tt,
        "details": muc.get("reason") or "",
    }
    if muc.get("progress") is not None:
        ra["progress"] = muc["progress"]
    if tt == "blocked":
        # blocker lấy từ SSOT; nếu thiếu thì nói rõ chứ không bịa lý do.
        ra["blocker"] = muc.get("blocked_reason") or "Chưa ghi lý do chặn"
    return ra


def _thong_bao_tu_lich(su_kien: dict) -> dict[str, Any]:
    return {
        "id": f"sched-{su_kien.get('id')}",
        "source": "Discord",
        "type": su_kien.get("event_type") or "Sự kiện",
        "title": su_kien.get("title") or "(không có tiêu đề)",
        "time": _gio_viet(su_kien.get("starts_at")),
        "status": "upcoming",
        "details": f"Mốc {su_kien.get('event_type')} của "
                   f"{su_kien.get('team_name') or 'toàn chương trình'}.",
    }


def _tasks_trong_tuan(tat_ca: list[dict], dau: dt.date | None, cuoi: dt.date | None) -> list[str]:
    """Tiêu đề task THẬT có hạn rơi vào tuần đó (khử trùng lặp, tối đa 4)."""
    if not dau or not cuoi:
        return []
    ra: list[str] = []
    for t in tat_ca:
        try:
            d = dt.datetime.fromisoformat(str(t.get("deadline")).replace("Z", "")).date()
        except (ValueError, TypeError):
            continue
        if dau <= d <= cuoi and t.get("title") and t["title"] not in ra:
            ra.append(t["title"])
    return ra[:4]


def _tien_do_tuan(tat_ca: list[dict], dau, cuoi) -> int | None:
    """% task đã xong trong tuần. None nếu tuần đó không có task nào."""
    if not dau or not cuoi:
        return None
    trong_tuan = []
    for t in tat_ca:
        try:
            d = dt.datetime.fromisoformat(str(t.get("deadline")).replace("Z", "")).date()
        except (ValueError, TypeError):
            continue
        if dau <= d <= cuoi:
            trong_tuan.append(t)
    if not trong_tuan:
        return None
    xong = sum(1 for t in trong_tuan if t.get("status") == "done")
    return round(100 * xong / len(trong_tuan))


def cham_diem_task(yeu_cau: dict[str, Any]) -> dict[str, Any]:
    """Chấm ưu tiên cho 1 task bằng rule engine THẬT của agent (agent/priority.py).

    Dùng cho POST /api/strategy. Trả về đúng schema cũ {task, priority, reason,
    steps} để strategy.html không phải sửa. Nếu không import được agent thì nói
    rõ trong reason chứ không giả vờ đã chấm.
    """
    tieu_de = (yeu_cau.get("task_title") or "").strip()
    muc_do = (yeu_cau.get("importance") or "medium").strip()
    blocker = (yeu_cau.get("blocker") or "").strip()
    han = (yeu_cau.get("deadline") or "").strip()

    # importance dạng chữ của UI -> thang 1..5 của SSOT.
    THANG = {"low": 2, "medium": 3, "high": 5}
    task = {
        "id": 0,
        "title": tieu_de,
        "priority": THANG.get(muc_do, 3),
        "status": "blocked" if blocker else "todo",
        "due_at": han or None,
        "blocked_since": (dt.datetime.utcnow() - dt.timedelta(days=1)).isoformat(sep=" ")
                         if blocker else None,
        "team_id": None,
    }

    if agent_core is None:
        return {
            "task": tieu_de,
            "priority": "high" if blocker else muc_do,
            "reason": f"Chưa chấm được bằng rule engine ({AGENT_ERROR}).",
            "steps": ["Kiểm tra lại cấu hình agent trước khi dùng gợi ý này."],
        }

    from agent import priority as agent_priority

    # Mốc thật từ SSOT để luật milestone_impact có dữ liệu mà chấm.
    moc: list[dict] = []
    if agent_tools is not None:
        try:
            for ms in agent_tools.get_upcoming_milestones(limit=10):
                ms["_starts"] = _parse_iso(ms.get("starts_at"))
                moc.append(ms)
        except Exception:  # noqa: BLE001 - thiếu mốc thì vẫn chấm được
            moc = []

    da_cham = agent_priority.score_task(task, agent_priority.utc_now(), moc)
    diem = da_cham["agent_score"]

    # Ngưỡng lấy từ chính thang điểm của rule engine (quá hạn = 1000+).
    if diem >= 1000:
        muc_ket = "high"
    elif diem >= 300:
        muc_ket = "high" if blocker else "medium"
    else:
        muc_ket = "low" if diem < 60 else muc_do

    buoc: list[str] = []
    luat = da_cham.get("agent_rules", [])
    if "overdue" in luat:
        buoc.append("Task đã quá hạn — chốt lại deadline mới và bước nhỏ tiếp theo ngay hôm nay.")
    if blocker:
        buoc.append(f"Gỡ blocker '{blocker}' trước khi làm tiếp phần còn lại.")
    if "milestone_impact" in luat:
        buoc.append("Task này ảnh hưởng tới một mốc sắp tới — báo mentor nếu có nguy cơ trễ.")
    if "due_soon" in luat or "due_today" in luat:
        buoc.append("Đặt một block thời gian trong hôm nay để hoàn thành.")
    if not buoc:
        buoc.append("Chưa có tín hiệu khẩn cấp — tiếp tục theo kế hoạch và cập nhật tiến độ.")

    return {
        "task": tieu_de,
        "priority": muc_ket,
        "reason": da_cham["agent_reason"],
        "steps": buoc,
        "score": diem,
        "rules_fired": luat,
    }


def _parse_iso(ts) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", ""))
    except ValueError:
        return None


def _so_lieu_ssot(user_id: int | None) -> dict[str, int]:
    """Đếm khối lượng việc THẬT của một người, đọc thẳng SSOT (chỉ đọc).

    Dùng cho phần chiến lược: dashboard chỉ hiển thị 4 nhóm task nên đếm theo
    thẻ hiển thị sẽ báo thiếu. Đây là con số đầy đủ.
    """
    trong = {"tong": 0, "qua_han": 0, "bi_chan": 0}
    if user_id is None or agent_tools is None:
        return trong
    import sqlite3
    duong_dan = Path(agent_tools.SSOT_DB_PATH)
    if not duong_dan.exists():
        return trong
    con = sqlite3.connect(f"file:{duong_dan}?mode=ro", uri=True)
    try:
        hang = con.execute(
            """SELECT
                 (SELECT COUNT(*) FROM tasks WHERE assignee_id=? AND status<>'done'),
                 (SELECT COUNT(*) FROM tasks WHERE assignee_id=? AND status<>'done'
                    AND due_at IS NOT NULL AND due_at < datetime('now')),
                 (SELECT COUNT(*) FROM tasks WHERE assignee_id=? AND status='blocked')""",
            (user_id, user_id, user_id)).fetchone()
        return {"tong": hang[0] or 0, "qua_han": hang[1] or 0, "bi_chan": hang[2] or 0}
    except sqlite3.Error as exc:
        log.warning("Không đếm được số liệu SSOT cho user %s: %s", user_id, exc)
        return trong
    finally:
        con.close()


def _chien_luoc_ca_nhan(ho_so: dict | None, thong_bao: list[dict],
                        ket_qua: dict) -> dict[str, Any]:
    """Gợi ý chiến lược THEO TỪNG NGƯỜI, suy ra bằng luật từ SSOT + hồ sơ.

    Không gọi LLM: mọi câu đều bám vào con số đếm được của chính người đó
    (số task quá hạn / bị chặn / sắp đến hạn) cộng với vai trò và thói quen
    học trong hồ sơ. Người khác hồ sơ hoặc khác khối lượng việc -> khác kết quả.
    """
    if not ho_so:
        return {
            "muc_do_rui_ro": "khong_xac_dinh",
            "tom_tat": "Chưa xác định được người dùng nên chưa cá nhân hoá được gợi ý.",
            "viec_can_lam": ["Đăng nhập bằng tài khoản trong users_seed.json để xem gợi ý riêng."],
            "canh_bao": ["Đang dùng dữ liệu chung của cả chương trình."],
        }

    # Số liệu lấy TRỰC TIẾP từ SSOT chứ không đếm thẻ hiển thị: dashboard chỉ
    # nêu 4 nhóm (quá hạn / hôm nay / sắp tới / trong tuần), nên task đến hạn
    # xa hơn sẽ không có thẻ và đếm theo thẻ sẽ báo thiếu khối lượng việc thật.
    so = _so_lieu_ssot(ho_so.get("user_id"))
    tong, qua_han, bi_chan = so["tong"], so["qua_han"], so["bi_chan"]
    sap_han = sum(1 for n in thong_bao if n.get("status") == "upcoming"
                  and n.get("source") == "VLearn")

    # Mức rủi ro suy từ chính số liệu của người này (ngưỡng cố định, tái lập được).
    if qua_han >= 2 or bi_chan >= 2:
        rui_ro = "cao"
    elif qua_han or bi_chan:
        rui_ro = "trung_binh"
    else:
        rui_ro = "thap"

    viec: list[str] = []
    canh_bao: list[str] = []
    la_truong_nhom = ho_so.get("role_key") == "leader"

    if bi_chan:
        canh_bao.append(f"Bạn đang có {bi_chan} task bị chặn.")
        viec.append(f"Gỡ {bi_chan} task bị chặn trước — đây là nút thắt lớn nhất của bạn.")
        if la_truong_nhom:
            viec.append("Với vai trò trưởng nhóm, báo blocker này trong stand-up để cả nhóm cùng gỡ.")
    if qua_han:
        canh_bao.append(f"Bạn có {qua_han} task đã quá hạn.")
        viec.append(f"Chốt lại deadline mới cho {qua_han} task quá hạn ngay hôm nay.")
    if sap_han:
        viec.append(f"Chuẩn bị trước cho {sap_han} task sắp đến hạn.")

    # Thói quen học -> cách sắp xếp thời gian, lấy nguyên văn từ hồ sơ.
    thoi_quen = ho_so.get("study_habits", "")
    if "buổi tối" in thoi_quen:
        viec.append("Theo thói quen của bạn, xếp phần khó vào khối buổi tối không bị ngắt.")
    elif "buổi sáng" in thoi_quen:
        viec.append("Theo thói quen của bạn, chia nhỏ task 30 phút và xử lý sớm buổi sáng.")
    elif "deadline" in thoi_quen:
        viec.append("Bạn hay dồn việc sát hạn — đặt nhắc trước 2 ngày cho mốc gần nhất.")
    elif "review chéo" in thoi_quen:
        viec.append("Bạn làm tốt khi review chéo — rủ một đồng đội cùng soát phần đang làm.")

    if not viec:
        viec.append("Không có tín hiệu khẩn cấp — tiếp tục theo kế hoạch tuần.")

    return {
        "muc_do_rui_ro": rui_ro,
        "tom_tat": (f"{ho_so.get('display_name')} ({ho_so.get('role')}, "
                    f"{ho_so.get('team_name')}): {tong} task đang mở, "
                    f"{qua_han} quá hạn, {bi_chan} bị chặn."),
        "nen_tang": ho_so.get("background", ""),
        "viec_can_lam": viec,
        "canh_bao": canh_bao,
        "so_lieu": {"tong": tong, "qua_han": qua_han, "bi_chan": bi_chan, "sap_han": sap_han},
    }


def _doc_timeline() -> list[dict]:
    if not TIMELINE_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy {TIMELINE_PATH}")
    return json.loads(TIMELINE_PATH.read_text(encoding="utf-8")).get("timeline", [])


def build_dashboard(mode: str = "weekly", top_n: int = 60,
                    username: str | None = None) -> dict[str, Any]:
    """Ghép lộ trình + task thật thành payload cho index.html.

    Luôn trả về đủ khoá weeks/notifications/meta. Lỗi ở một nguồn thì ghi vào
    meta.warnings chứ không ném exception làm hỏng cả trang.
    """
    canh_bao: list[str] = []
    nam = _nam_moc()
    ho_so = lay_ho_so(username)
    if username and ho_so is None:
        canh_bao.append(
            f"Tài khoản '{username}' không có hồ sơ trong users_seed.json — "
            "hiển thị dữ liệu chung của cả chương trình, chưa cá nhân hoá.")

    # --- 1. Task thật từ agent (đọc SSOT) --------------------------------
    ket_qua: dict[str, list] = {}
    if agent_core is None:
        canh_bao.append(f"Không dùng được agent ({AGENT_ERROR}); danh sách nhắc việc trống.")
    else:
        try:
            ket_qua = agent_core.run(mode=mode, top_n=top_n)
        except Exception as exc:  # noqa: BLE001
            canh_bao.append(f"Agent lỗi: {type(exc).__name__}: {exc}")
            log.exception("agent.run thất bại")

    # --- 1b. Thu hẹp về đúng người đang đăng nhập ------------------------
    # Đây là chỗ ngữ cảnh người dùng thành BẮT BUỘC: cùng một endpoint nhưng
    # mỗi tài khoản chỉ thấy task của chính mình -> output khác nhau.
    if ho_so:
        ten_hien = ho_so.get("display_name")
        for khoa in ("overdue_alerts", "today_items", "due_soon_alerts", "week_items"):
            ket_qua[khoa] = [m for m in ket_qua.get(khoa, [])
                             if m.get("assignee") == ten_hien]

    thong_bao: list[dict] = []
    da_co: set[str] = set()
    # Thứ tự ưu tiên hiển thị: quá hạn -> hôm nay -> sắp tới.
    for nhom, khoa in (("overdue", "overdue_alerts"), ("today", "today_items"),
                       ("due_soon", "due_soon_alerts")):
        for muc in ket_qua.get(khoa, []):
            tb = _thong_bao_tu_task(muc, nhom)
            if tb["id"] not in da_co:
                da_co.add(tb["id"])
                thong_bao.append(tb)

    # --- 2. Lịch sự kiện thật từ SSOT ------------------------------------
    if agent_tools is not None:
        try:
            for sk in agent_tools.get_upcoming_milestones(limit=10):
                # Mốc toàn chương trình (team_id None) hoặc đúng team của mình.
                if ho_so and sk.get("team_id") not in (None, ho_so.get("team_id")):
                    continue
                thong_bao.append(_thong_bao_tu_lich(sk))
        except Exception as exc:  # noqa: BLE001
            canh_bao.append(f"Không đọc được lịch sự kiện: {type(exc).__name__}")

    # --- 3. Lộ trình 6 tuần ----------------------------------------------
    moi_task = [m for k in ("overdue_alerts", "today_items", "due_soon_alerts", "week_items")
                for m in ket_qua.get(k, [])]
    tuan: list[dict] = []
    try:
        for muc in _doc_timeline():
            dau, cuoi = _khoang_ngay(muc.get("range", ""), nam)
            tt = TRANG_THAI_TUAN.get(str(muc.get("status", "")).strip().lower(), "upcoming")
            w: dict[str, Any] = {
                "id": muc.get("week"),
                "week": f"Tuần {muc.get('week')}",
                "date": muc.get("range") or "Chưa xác định",
                "title": muc.get("milestone") or "",
                "status": tt,
                "milestone": muc.get("gate") or muc.get("milestone") or "",
                "desc": muc.get("focus") or "",
                "tasks": _tasks_trong_tuan(moi_task, dau, cuoi),
            }
            if muc.get("action"):
                w["subtitle"] = muc["action"]
            td = _tien_do_tuan(moi_task, dau, cuoi)
            if td is not None:
                w["progress"] = td
            tuan.append(w)
    except Exception as exc:  # noqa: BLE001
        canh_bao.append(f"Không đọc được lộ trình: {type(exc).__name__}: {exc}")
        log.exception("đọc timeline thất bại")

    return {
        "weeks": tuan,
        "notifications": thong_bao,
        "meta": {
            "user": ho_so,
            "strategy": _chien_luoc_ca_nhan(ho_so, thong_bao, ket_qua),
            "personalized": bool(ho_so),
            "mode": mode,
            "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sources": [s.get("ref") for s in ket_qua.get("sources_used", [])],
            "task_count": len(thong_bao),
            "warnings": canh_bao,
        },
    }
