#!/usr/bin/env python3
"""Runnable test suite for the RAG chatbot (`POST /api/query`).

`cases.json` is the human-readable spec: question, expected_answer_points,
category, difficulty, notes. It is deliberately kept as a plain JSON array so it
can be handed to a reviewer, imported into a sheet, or diffed on its own.

This file holds the *machine-checkable* half: one CHECKS entry per case id. The
runner refuses to start if the two drift apart, so a case can never be documented
without being executed (same guard as agent/evals/run_evals.py).

Assertions are PROPERTY checks, not exact-string matches — LLM output is not
deterministic. Each check asks only: did the right chunk get retrieved, are the
exact figures from the corpus present, and is anything fabricated?

Usage:
    python3 rag-app/evals/run_cases.py                    # run everything
    python3 rag-app/evals/run_cases.py --only TC02        # prefix filter
    python3 rag-app/evals/run_cases.py --category adversarial
    python3 rag-app/evals/run_cases.py --json report.json
    python3 rag-app/evals/run_cases.py --allow-known-fail # KNOWN_FAILURES -> XFAIL
    RAG_BASE_URL=http://127.0.0.1:8010 python3 rag-app/evals/run_cases.py

Exit code: 1 if any case FAILs, else 0. SKIP never fails the run — a backend
that is down, or an unconfigured OPENAI_API_KEY, is not a defect in the chatbot.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES: list[dict] = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
BASE_URL = os.getenv("RAG_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
TIMEOUT = int(os.getenv("RAG_EVAL_TIMEOUT", "60"))

PASS, FAIL, SKIP, XFAIL = "PASS", "FAIL", "SKIP", "XFAIL"

# Cases that fail against the current prompt for a reason already tracked
# elsewhere. Listed here so the failure is visible, never silently green.
KNOWN_FAILURES = {
    "TC022": "Corpus có hai ngày Demo Day mâu thuẫn; prompt hiện chưa buộc bot "
             "nêu cả hai. Trùng lỗi EV-NEG-004 trong agent/evals.",
}

# Cụm từ mà SYSTEM_PROMPT cho phép dùng khi tài liệu không phủ được câu hỏi.
# Đây là kiểm tra TÍNH CHẤT: chỉ cần bot nói rõ "tài liệu không có", không bắt
# đúng một câu chữ cố định.
DECLINE_PHRASES = (
    "không tìm thấy", "không có trong tài liệu", "không đề cập", "không nhắc",
    "không cung cấp", "không có thông tin", "chưa nói đủ", "không nêu rõ",
    "không nói rõ", "không thể cung cấp", "chưa đề cập", "không quy định",
    "không chỉ định", "không ghi rõ", "tài liệu không",
)

# Nhãn tách bạch phần mở rộng, theo SYSTEM_PROMPT trong rag-app/backend/app/llm.py.
EXTENSION_MARKERS = DECLINE_PHRASES + (
    "[mở rộng]", "mở rộng:", "kiến thức chung", "theo kinh nghiệm",
    "ngoài tài liệu", "[từ tài liệu]",
)

CONFLICT_MARKERS = ("mâu thuẫn", "không khớp", "khác nhau", "trái ngược",
                    "không thống nhất", "chưa nhất quán")

# Regex chống bịa, dùng lại ở nhiều case.
RE_CLOCK = re.compile(r"\b\d{1,2}\s*(?::\s*\d{2}|h\s*\d{0,2}\b|giờ\b)")
RE_WEATHER = re.compile(r"\d+\s*(?:°|độ c\b|độ\b|mm mưa)")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RE_PHONE = re.compile(r"\b0\d[\d .-]{7,}\d\b")
RE_PENALTY = re.compile(r"(?:trừ|giảm)\s*\d+|\d+\s*%|\d+\s*điểm")


# ---------------------------------------------------------------- transport
def http(question: str, top_k: int) -> tuple[int, dict]:
    body = json.dumps({"question": question, "top_k": top_k}).encode()
    req = urllib.request.Request(BASE_URL + "/api/query", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, {}
    except Exception as exc:  # noqa: BLE001
        raise ConnectionError(str(exc)) from exc


def backend_state() -> tuple[bool, bool]:
    """(reachable, generating_with_ai). Retrieval cases run in either mode;
    answer-content cases cannot be graded when the backend is in fallback."""
    try:
        _, d = http("ping", 1)
    except ConnectionError:
        return False, False
    return True, d.get("mode") == "ai"


# ---------------------------------------------------------------- matching
def norm(text: str) -> str:
    """Casefold + collapse whitespace + unify dash/quote variants, so a check
    string is not defeated by punctuation the model happened to choose."""
    t = unicodedata.normalize("NFC", text or "").casefold()
    t = t.replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", t)


def refs_of(data: dict) -> list[str]:
    return [f"{s.get('source_file', '')}{s.get('source_pointer', '')}"
            for s in data.get("sources", [])]


def grade(check: dict, data: dict) -> tuple[bool, list[str]]:
    """Apply one CHECKS entry. Returns (ok, list of failure reasons)."""
    answer = norm(data.get("answer", ""))
    refs = refs_of(data)
    bad: list[str] = []

    any_refs = check.get("retrieve_any")
    if any_refs and not any(r in refs for r in any_refs):
        bad.append(f"không truy xuất được đoạn nào trong {any_refs} (top={refs[:2]})")

    for ref in check.get("retrieve_all", []):
        if ref not in refs:
            bad.append(f"thiếu chunk bắt buộc {ref}")

    missing = [s for s in check.get("all", []) if norm(s) not in answer]
    if missing:
        bad.append("thiếu: " + ", ".join(missing))

    for group in check.get("any_groups", []):
        if not any(norm(s) in answer for s in group):
            bad.append("thiếu một trong: " + " | ".join(group))

    present = [s for s in check.get("none", []) if norm(s) in answer]
    if present:
        bad.append("xuất hiện nội dung cấm: " + ", ".join(present))

    for pattern in check.get("none_regex", []):
        m = re.search(pattern, answer)
        if m:
            bad.append(f"bịa đặt/khớp mẫu cấm {pattern!r} tại {m.group(0)!r}")

    if check.get("decline") and not any(p in answer for p in DECLINE_PHRASES):
        bad.append("không nói rõ tài liệu thiếu thông tin")

    if check.get("extension_label") and not any(p in answer for p in EXTENSION_MARKERS):
        bad.append("không tách bạch phần mở rộng khỏi phần lấy từ tài liệu")

    if check.get("conflict"):
        sides = check["conflict"]
        seen = [any(norm(v) in answer for v in side) for side in sides]
        flagged = any(m in answer for m in CONFLICT_MARKERS)
        if not (all(seen) or flagged):
            bad.append(f"không nêu cả hai nguồn mâu thuẫn (thấy={seen}, gắn cờ={flagged})")

    if check.get("clarifies") and "?" not in (data.get("answer") or ""):
        bad.append("không hỏi lại để làm rõ")

    return not bad, bad


# ------------------------------------------------------------------ checks
# Một entry cho mỗi case id trong cases.json. Khoá:
#   top_k           số đoạn truy xuất (mặc định 5)
#   retrieve_all    mọi ref phải nằm trong sources — chấm được cả ở chế độ fallback
#   retrieve_any    ít nhất một ref phải nằm trong sources
#   all             mọi chuỗi phải có trong answer          (cần mode="ai")
#   any_groups      mỗi nhóm phải có ít nhất một chuỗi      (cần mode="ai")
#   none / none_regex   nội dung/mẫu KHÔNG được xuất hiện   (cần mode="ai")
#   decline         phải nói rõ tài liệu không có thông tin (cần mode="ai")
#   extension_label phải tách [Từ tài liệu] / [Mở rộng]     (cần mode="ai")
#   conflict        danh sách các nhóm giá trị của từng nguồn mâu thuẫn
#   clarifies       phải hỏi lại người dùng
Q = "cohort3_quality_control_demo_day.json"
X = "cohort3_xp_system.json"
T = "cohort3_team_and_topic_selection.json"
W = "cohort3_weekly_runbook.json"
D = "cohort3_discord_commands.json"
C = "cohort3_evening_calendar.json"
K = "cohort3_knowledge_base.json"
M = "master_timeline.json"

CHECKS: dict[str, dict] = {
    "TC001": {"retrieve_all": [f"{Q}/blocks/0"],
              "all": ["không chặn"],
              "none_regex": [r"(?<!không )chặn team", r"(?<!không )chặn nhóm"]},
    "TC002": {"retrieve_all": [f"{X}/blocks/0"],
              "any_groups": [["+5 xp", "5 xp"]],
              "none_regex": [r"\b50\s*xp"]},
    "TC003": {"retrieve_all": [f"{X}/blocks/0"],
              "all": ["5 xp", "10 xp", "100 xp"],
              "any_groups": [["workshop"], ["cộng đồng"]]},
    "TC004": {"retrieve_all": [f"{X}/blocks/1"],
              "all": ["1000", "star builder"]},
    "TC005": {"retrieve_all": [f"{X}/blocks/1"],
              "all": ["200", "500", "1000", "1500",
                      "active builder", "solid builder", "star builder", "elite builder"]},
    "TC006": {"retrieve_all": [f"{T}/sections/1"],
              "any_groups": [["p-xxx", "p-042"]]},
    "TC007": {"retrieve_all": [f"{T}/sections/1"],
              "all": ["c3-app", "c4-app"]},
    "TC008": {"retrieve_all": [f"{T}/sections/0"],
              "any_groups": [["2 team", "tối đa 2", "hai team"]]},
    "TC009": {"retrieve_all": [f"{M}/operating_notes/2"],
              "all": ["bắt buộc"],
              "any_groups": [["mentor"], ["xp"]]},
    "TC010": {"retrieve_all": [f"{Q}/blocks/1"],
              "any_groups": [["người dùng"], ["hoàn thiện sản phẩm", "sản phẩm"],
                             ["ai"], ["hạ tầng"], ["code"]]},
    "TC011": {"retrieve_all": [f"{Q}/blocks/2"],
              "all": ["source code", "readme", "kiến trúc", "kiểm thử",
                      "live url", "video demo", "pitch deck", "ai log"],
              "any_groups": [["đặc tả", "thiết kế"], ["nhật ký"]]},
    "TC012": {"retrieve_all": [f"{C}/chunks/0"],
              "all": ["20/07", "05/09", "23/07"]},
    "TC013": {"retrieve_all": [f"{K}/documents/3/sections/0"],
              "any_groups": [["stand up", "stand-up", "standup"], ["deadline"],
                             ["active"], ["at-risk", "at risk", "rủi ro"]]},
    "TC014": {"retrieve_all": [f"{M}/timeline/1"],
              "all": ["gate 1"],
              "any_groups": [["30/07"], ["chốt đề tài", "chốt đề"]]},

    "TC015": {"retrieve_all": [f"{T}/sections/0"],
              "all": ["25/07"],
              "any_groups": [["tự động"], ["đề tài", "ngân hàng đề"]]},
    "TC016": {"retrieve_all": [f"{W}/blocks/0"],
              "any_groups": [["hôm qua", "đã làm"], ["hôm nay", "đang làm"],
                             ["vấn đề", "khó khăn", "blocker", "kẹt", "vướng"]]},
    "TC017": {"retrieve_all": [f"{W}/blocks/1"],
              "any_groups": [["weekly", "báo cáo tuần"], ["coaching"],
                             ["6 tuần", "sáu tuần", "cố định"]]},
    "TC018": {"retrieve_all": [f"{D}/blocks/3"],
              "all": ["/gate submit", "/gate status"],
              "none_regex": [r"/gate\s+(delete|remove|xoá)"]},
    "TC019": {"retrieve_all": [f"{D}/blocks/0"],
              "all": ["/weekly submit", "/weekly view", "/weekly update",
                      "/weekly history", "/weekly suggest"],
              "none_regex": [r"/weekly\s+(delete|remove|xoá)"]},
    "TC020": {"retrieve_all": [f"{D}/blocks/4"],
              "all": ["/ticket create"]},
    "TC021": {"retrieve_all": [f"{W}/blocks/3"],
              "any_groups": [["kick-off", "kick off", "kickoff"], ["rag"],
                             ["agent"], ["pitch"]]},

    "TC022": {"top_k": 5,
              "retrieve_all": [f"{C}/chunks/1", f"{M}/timeline/5"],
              "conflict": [["03/09", "04/09", "05/09"], ["01/09"]]},
    "TC023": {"retrieve_all": [f"{C}/events/2"],
              "decline": True,
              "none_regex": [RE_CLOCK.pattern]},
    "TC024": {"decline": True,
              "none_regex": [RE_PENALTY.pattern]},
    "TC025": {"any_groups": [["gate 1", "gate 2", "demo day", "tuần"]],
              "extension_label": True},
    "TC026": {"clarifies": True,
              "none_regex": [r"23\s*:\s*59", r"17\s*:\s*00", r"\bgiao cho\b"]},
    "TC027": {"retrieve_all": [f"{T}/sections/1"],
              "all": ["p-042", "c3-app-042"],
              "any_groups": [["không phải", "khác nhau", "khác loại", "hai thứ khác"]]},

    "TC028": {"retrieve_all": [f"{Q}/blocks/0"],
              "all": ["không chặn"],
              "none_regex": [r"(?<!không )bị loại", r"(?<!không )loại khỏi chương trình"]},
    "TC029": {"retrieve_all": [f"{X}/blocks/0"],
              "any_groups": [["+5 xp", "5 xp"]],
              "none_regex": [r"(?<!không phải )(?<!không phải là )\b50\s*xp\b(?!.{0,40}(không|sai))"]},
    "TC030": {"decline": True,
              "none_regex": [RE_CLOCK.pattern]},
    "TC031": {"decline": True,
              "none_regex": [RE_EMAIL.pattern, RE_PHONE.pattern]},
    "TC032": {"decline": True},

    "TC033": {"extension_label": True,
              "any_groups": [["chunk"], ["overlap", "chồng lấn", "chồng lặp"]]},
    "TC034": {"retrieve_any": [f"{Q}/blocks/2"],
              "extension_label": True,
              "any_groups": [["deliverable", "10 "]]},
    "TC035": {"extension_label": True,
              "any_groups": [["vấn đề", "problem"], ["demo"]]},
    "TC036": {"extension_label": True,
              "any_groups": [["stand up", "stand-up", "standup", "weekly", "báo cáo tuần"]]},
    "TC037": {"extension_label": True,
              "any_groups": [["chroma", "pgvector", "qdrant", "faiss",
                              "weaviate", "milvus", "pinecone"]]},
    "TC038": {"retrieve_any": [f"{Q}/blocks/2", f"{M}/operating_notes/0"],
              "all": ["ai log"],
              "extension_label": True},
    "TC039": {"retrieve_any": [f"{Q}/blocks/2"],
              "all": ["readme"],
              "extension_label": True},
    "TC040": {"decline": True,
              "none_regex": [RE_WEATHER.pattern]},
}

# Khoá nào cần bot thực sự sinh câu trả lời (mode="ai") mới chấm được.
CONTENT_KEYS = {"all", "any_groups", "none", "none_regex", "decline",
                "extension_label", "conflict", "clarifies"}


def needs_ai(check: dict) -> bool:
    return bool(CONTENT_KEYS & set(check))


# -------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chạy bộ test cho RAG chatbot.")
    ap.add_argument("--only", help="lọc theo tiền tố id, ví dụ TC02")
    ap.add_argument("--category", help="lọc theo category")
    ap.add_argument("--json", help="ghi báo cáo máy đọc được ra file này")
    ap.add_argument("--allow-known-fail", action="store_true",
                    help="hạ các case trong KNOWN_FAILURES xuống XFAIL")
    args = ap.parse_args(argv)

    spec_ids = {c["id"] for c in CASES}
    if spec_ids != set(CHECKS):
        print(f"spec/impl lệch nhau — chưa cài đặt: {sorted(spec_ids - set(CHECKS))}, "
              f"không có trong cases.json: {sorted(set(CHECKS) - spec_ids)}", file=sys.stderr)
        return 2

    selected = [c for c in CASES
                if (not args.only or c["id"].startswith(args.only))
                and (not args.category or c["category"] == args.category)]

    reachable, ai = backend_state()
    print(f"RAG: {BASE_URL}   reachable={reachable}   mode={'ai' if ai else 'fallback/none'}")
    dist: dict[str, int] = {}
    for c in CASES:
        dist[c["category"]] = dist.get(c["category"], 0) + 1
    in_ctx = dist.get("in_context_factual", 0) + dist.get("in_context_procedural", 0)
    ooc = dist.get("out_of_context_creative", 0)
    print(f"{len(CASES)} cases — in_context {in_ctx} ({in_ctx / len(CASES):.0%}), "
          f"out_of_context_creative {ooc} ({ooc / len(CASES):.0%}), "
          f"edge {dist.get('edge_case', 0)}, adversarial {dist.get('adversarial', 0)}\n")

    results, counts = [], {PASS: 0, FAIL: 0, SKIP: 0, XFAIL: 0}
    for case in selected:
        cid = case["id"]
        check = CHECKS[cid]
        if not reachable:
            status, detail = SKIP, "backend không truy cập được"
        elif needs_ai(check) and not ai:
            status, detail = SKIP, "backend đang ở chế độ fallback — không chấm nội dung được"
        else:
            try:
                code, data = http(case["question"], check.get("top_k", 5))
            except ConnectionError as exc:
                status, detail = SKIP, f"lỗi kết nối: {exc}"
            else:
                if code != 200:
                    status, detail = FAIL, f"HTTP {code}"
                else:
                    ok, reasons = grade(check, data)
                    status = PASS if ok else FAIL
                    detail = "ok" if ok else "; ".join(reasons)
        if status == FAIL and args.allow_known_fail and cid in KNOWN_FAILURES:
            status, detail = XFAIL, f"lỗi đã biết — {KNOWN_FAILURES[cid]} | {detail}"

        counts[status] += 1
        results.append({"id": cid, "category": case["category"],
                        "difficulty": case["difficulty"], "status": status,
                        "detail": detail, "question": case["question"]})
        print(f"{status:5} {cid}  [{case['category']}] {case['question'][:52]}")
        if status != PASS:
            print(f"        {detail[:180]}")

    print(f"\n{counts[PASS]} PASS · {counts[FAIL]} FAIL · "
          f"{counts[SKIP]} SKIP · {counts[XFAIL]} XFAIL  ({len(selected)} cases)")
    still_failing = [r["id"] for r in results if r["status"] == FAIL and r["id"] in KNOWN_FAILURES]
    if still_failing:
        print(f"Lỗi đã biết, chưa sửa: {', '.join(still_failing)}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"base_url": BASE_URL, "backend_reachable": reachable, "ai_mode": ai,
             "counts": counts, "known_failures": KNOWN_FAILURES, "results": results},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"báo cáo -> {args.json}")

    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
