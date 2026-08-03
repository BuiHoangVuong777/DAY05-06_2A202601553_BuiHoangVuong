from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

import dashboard_data          # lớp ánh xạ dữ liệu thật -> schema UI


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

log = logging.getLogger("vlearn")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="AI Study Progress Assistant",
    version="1.1.0",
)

# --------------------------------------------------------------------------
# Đăng nhập — XÁC THỰC GIẢ LẬP
#
# Dự án chưa có hệ thống xác thực thật, nên đây là auth mô phỏng, được bật
# tường minh bằng biến môi trường. Không hardcode mật khẩu thật ở đây.
#   DEV_AUTH=true|false   bật/tắt đăng nhập giả lập (mặc định true cho demo)
#   DEV_AUTH_USERNAME     tên đăng nhập demo
#   DEV_AUTH_PASSWORD     mật khẩu demo
#   SESSION_SECRET        khoá ký cookie phiên; bỏ trống sẽ sinh ngẫu nhiên
# --------------------------------------------------------------------------
DEV_AUTH = os.getenv("DEV_AUTH", "true").strip().lower() in {"1", "true", "yes"}
# Tài khoản dự phòng khi không đọc được users_seed.json (mỗi người một mật khẩu
# riêng nằm trong file seed đó, xem codebase/users_seed.json).
DEV_AUTH_USERNAME = os.getenv("DEV_AUTH_USERNAME", "vlearn").strip()
DEV_AUTH_PASSWORD = os.getenv("DEV_AUTH_PASSWORD", "vlearn-dev").strip()

# Bỏ trống SESSION_SECRET thì sinh khoá ngẫu nhiên: an toàn hơn khoá cứng,
# đổi lại phiên đăng nhập không sống sót qua lần khởi động lại server.
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip() or secrets.token_urlsafe(32)
if not os.getenv("SESSION_SECRET", "").strip():
    log.warning("Chưa đặt SESSION_SECRET — dùng khoá ngẫu nhiên, phiên sẽ mất khi khởi động lại.")
if DEV_AUTH:
    log.warning("DEV_AUTH đang BẬT — đăng nhập là giả lập, không phải tài khoản VLearn thật.")

# Trang và tài nguyên không cần đăng nhập.
PUBLIC_PATHS = {"/login", "/logout", "/login.html", "/favicon.ico"}


def _dang_nhap_roi(request: Request) -> bool:
    return bool(request.session.get("user"))


@app.middleware("http")
async def chan_trang_chua_dang_nhap(request: Request, call_next):
    """Chặn trang HTML khi chưa đăng nhập và chuyển hướng về /login.

    Phải là middleware chứ không phải route guard: StaticFiles được mount ở "/"
    nên nó phục vụ index.html trước khi bất kỳ route nào chạy. Middleware chạy
    trước routing nên chặn được cả static mount.

    Phạm vi: chỉ chặn trang HTML. /api/* và tài nguyên tĩnh (.css/.js/.png…)
    vẫn mở như cũ, để không phá luồng gọi /api/strategy của strategy.html.
    """
    path = request.url.path
    la_trang_html = path == "/" or path.endswith(".html")
    if la_trang_html and path not in PUBLIC_PATHS and not _dang_nhap_roi(request):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


# THỨ TỰ MIDDLEWARE QUAN TRỌNG: add_middleware chèn vào đầu danh sách, nên cái
# đăng ký SAU sẽ chạy TRƯỚC. SessionMiddleware phải được thêm sau guard ở trên
# để nó nằm ngoài cùng và nạp request.session trước khi guard đọc.
# Đảo lại thứ tự này sẽ gây:
#   AssertionError: SessionMiddleware must be installed to access request.session
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="vlearn_session")


@app.get("/login")
def trang_dang_nhap(request: Request):
    """Hiển thị trang đăng nhập. Đã đăng nhập rồi thì về thẳng trang chính."""
    if _dang_nhap_roi(request):
        return RedirectResponse("/", status_code=303)
    return FileResponse(FRONTEND_DIR / "login.html")


@app.post("/login")
def xu_ly_dang_nhap(
    request: Request,
    # default="" thay vì Form(...): để trống thì tự xử lý và báo lỗi tiếng Việt,
    # thay vì FastAPI trả JSON 422 thô ngay trước khi vào hàm này.
    username: str = Form(default=""),
    password: str = Form(default=""),
):
    """Nhận form đăng nhập, kiểm tra bằng thông tin giả lập, rồi tạo phiên.

    Dùng Form(...) nên cần python-multipart (đã khai báo trong requirements.txt).
    """
    if not DEV_AUTH:
        # Không bật auth giả lập và dự án cũng chưa có auth thật -> từ chối rõ ràng,
        # tuyệt đối không cho qua ngầm.
        log.warning("Từ chối đăng nhập: DEV_AUTH=false và chưa có xác thực thật.")
        return RedirectResponse("/login?error=tat", status_code=303)

    username, password = username.strip(), password.strip()
    if not username or not password:
        return RedirectResponse("/login?error=thieu", status_code=303)

    # 1) Ưu tiên seed nhiều tài khoản: mỗi người một mật khẩu riêng.
    ho_so = dashboard_data.xac_thuc(username, password)
    if ho_so:
        request.session["user"] = ho_so["username"]
        request.session["user_id"] = ho_so["user_id"]
        log.info("Đăng nhập thành công: %r (user_id=%s, %s)",
                 ho_so["username"], ho_so["user_id"], ho_so["team_name"])
        return RedirectResponse("/", status_code=303)   # 303 để POST thành GET

    # 2) Tài khoản dự phòng từ biến môi trường (khi chưa có users_seed.json).
    if (secrets.compare_digest(username, DEV_AUTH_USERNAME)
            and secrets.compare_digest(password, DEV_AUTH_PASSWORD)):
        request.session["user"] = username
        request.session["user_id"] = None       # không gắn với người dùng nào trong SSOT
        log.info("Đăng nhập bằng tài khoản dự phòng: %r", username)
        return RedirectResponse("/", status_code=303)

    log.info("Đăng nhập thất bại cho tài khoản %r", username)
    return RedirectResponse("/login?error=sai", status_code=303)


@app.get("/logout")
def dang_xuat(request: Request):
    """Đăng xuất kiểu điều hướng: xoá phiên rồi quay về trang đăng nhập.

    Dùng khi mở thẳng bằng link/URL. Bản JSON cho JS là POST /api/logout.
    """
    request.session.clear()
    return RedirectResponse("/login?error=het_phien", status_code=303)


@app.post("/api/logout")
def dang_xuat_api(request: Request) -> dict:
    """Đăng xuất cho frontend: xoá phiên và trả JSON thay vì chuyển hướng.

    Tách khỏi GET /logout để nút bấm trong UI có thể xoá state cục bộ trước
    rồi mới tự điều hướng, không bị fetch đi theo redirect.
    """
    ten = request.session.get("user")
    request.session.clear()          # xoá luôn cả user_id
    log.info("Đăng xuất: %r", ten)
    return {"ok": True, "logged_in": False, "user": None, "redirect": "/login"}


@app.get("/api/me")
def thong_tin_phien(request: Request) -> dict:
    """Cho frontend tĩnh biết trạng thái đăng nhập hiện tại."""
    ho_so = dashboard_data.lay_ho_so(request.session.get("user"))
    return {
        "logged_in": _dang_nhap_roi(request),
        "user": request.session.get("user"),
        "user_id": request.session.get("user_id"),
        "profile": ho_so,          # None nếu đăng nhập bằng tài khoản dự phòng
        "dev_auth": DEV_AUTH,
    }


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


# Trợ lý AI (RAG) chạy ở service khác (rag-app). Gọi thẳng từ trình duyệt sẽ bị
# CORS chặn vì khác origin, nên proxy qua đây: cùng origin với dashboard, đồng
# thời tận dụng luôn phiên đăng nhập để chặn người chưa login.
# KHÔNG đụng vào logic AI/RAG — chỉ chuyển tiếp nguyên văn.
CHATBOT_API_URL = os.getenv("CHATBOT_API_URL", "http://127.0.0.1:8010/api/query").strip()
CHATBOT_TIMEOUT = float(os.getenv("CHATBOT_TIMEOUT", "60"))


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=4, ge=1, le=20)


@app.post("/api/chat")
def chat_proxy(request: Request, body: ChatRequest) -> dict:
    """Chuyển tiếp câu hỏi sang trợ lý RAG và trả nguyên response về UI."""
    if not _dang_nhap_roi(request):
        raise HTTPException(status_code=401, detail="Bạn cần đăng nhập để dùng trợ lý.")

    import requests  # đã có trong requirements.txt

    try:
        tra_loi = requests.post(CHATBOT_API_URL, json=body.model_dump(),
                                timeout=CHATBOT_TIMEOUT)
    except requests.RequestException as exc:
        log.warning("Không gọi được trợ lý tại %s: %s", CHATBOT_API_URL, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Không kết nối được tới trợ lý AI ({type(exc).__name__}). "
                   "Kiểm tra service rag-app còn chạy không.") from exc

    if tra_loi.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"Trợ lý AI trả lỗi HTTP {tra_loi.status_code}.")
    try:
        return tra_loi.json()
    except ValueError as exc:
        raise HTTPException(status_code=502,
                            detail="Trợ lý AI trả về dữ liệu không phải JSON.") from exc


@app.get("/api/dashboard")
def du_lieu_dashboard(request: Request, mode: str = "weekly") -> dict:
    """Dữ liệu THẬT cho index.html: lộ trình 6 tuần + nhắc việc từ SSOT.

    Thay cho mảng mock initialWeeks/initialNotifications trước đây trong
    index.html. Xem codebase/dashboard_data.py để biết cách ánh xạ schema.
    """
    if mode not in ("daily", "weekly"):
        raise HTTPException(status_code=422, detail="mode chỉ nhận 'daily' hoặc 'weekly'.")
    # Người đang đăng nhập là đầu vào BẮT BUỘC -> mỗi tài khoản ra kết quả khác nhau.
    try:
        return dashboard_data.build_dashboard(
            mode=mode, username=request.session.get("user"))
    except Exception as exc:  # noqa: BLE001
        log.exception("Không dựng được dashboard")
        raise HTTPException(status_code=500,
                            detail=f"Không lấy được dữ liệu dashboard: {exc}") from exc


class StrategyRequest(BaseModel):
    task_title: str = Field(min_length=1)
    deadline: str | None = None
    importance: str = "medium"
    status: str = "not_started"
    blocker: str | None = None


@app.post("/api/strategy")
def create_strategy(request: StrategyRequest) -> dict:
    """Chấm ưu tiên bằng RULE ENGINE THẬT của agent (agent/priority.py).

    Trước đây hàm này trả về vài câu cố định. Nay nó chấm điểm bằng đúng bộ
    luật agent dùng cho SSOT, nên lý do khớp với phần còn lại của hệ thống.
    Giữ nguyên schema cũ {task, priority, reason, steps} để strategy.html
    không phải sửa gì.
    """
    try:
        ket_qua = dashboard_data.cham_diem_task(request.model_dump())
    except Exception as exc:  # noqa: BLE001
        log.exception("Không chấm được ưu tiên")
        raise HTTPException(status_code=500, detail="Không thể tạo chiến lược.") from exc
    return ket_qua


# Đặt sau các API route để /api/... được xử lý trước.
app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)


if __name__ == "__main__":
    # Chạy trực tiếp `python3 server.py` cũng khởi động được server.
    # Trước đây file này không có phần này nên chạy xong là thoát ngay lập tức.
    import uvicorn

    uvicorn.run(
        "server:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("APP_RELOAD", "false").strip().lower() in {"1", "true", "yes"},
    )
