from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8000

# Thư mục chứa server.py, index.html, styles.css và public/
BASE_DIR = Path(__file__).resolve().parent


class NoCacheRequestHandler(SimpleHTTPRequestHandler):
    """Phục vụ file HTML/CSS/JS và tắt cache khi phát triển."""

    def end_headers(self) -> None:
        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate, max-age=0",
        )
        super().end_headers()


def main() -> None:
    # Đảm bảo server luôn phục vụ file bên trong thư mục codebase
    os.chdir(BASE_DIR)

    server = ThreadingHTTPServer(
        (HOST, PORT),
        NoCacheRequestHandler,
    )

    print("=" * 60)
    print("AI Study Progress Assistant")
    print(f"Đang phục vụ thư mục: {BASE_DIR}")
    print(f"Mở trình duyệt: http://{HOST}:{PORT}")
    print("Nhấn Ctrl + C để dừng server")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang dừng server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()