"""Answer generation with OpenAI, plus a clearly-labelled fallback.

Mirrors the invariant used elsewhere in this repo: when the model is unavailable,
the response says so (`mode: "fallback"`) instead of presenting canned text as AI output.
"""
from __future__ import annotations

import logging
from typing import Any

from app import config

log = logging.getLogger("rag.llm")

# Chính sách trả lời. LƯU Ý THAY ĐỔI HÀNH VI: bản trước chỉ cho phép trả lời
# trong phạm vi tài liệu và từ chối câu hỏi ngoài phạm vi. Bản này cho phép mở
# rộng bằng kiến thức chung, miễn là gắn nhãn tách bạch. Xem ghi chú ở README
# và eval EV-NEG-005 (đang khẳng định hành vi CŨ).
SYSTEM_PROMPT = (
    "Bạn là trợ lý AI trong hệ thống RAG của chương trình Cohort 3.\n"
    "\n"
    "ƯU TIÊN NGỮ CẢNH\n"
    "- Nếu câu trả lời có trong ngữ cảnh được cung cấp: coi đó là NGUỒN SỰ THẬT CHÍNH.\n"
    "  Trả lời cụ thể — nêu đúng con số, các bước, ràng buộc, ví dụ có trong ngữ cảnh.\n"
    "  Không được bỏ qua hoặc nói ngược lại ngữ cảnh.\n"
    "- Nếu ngữ cảnh thiếu hoặc không rõ: NÓI RÕ điều đó trước "
    "(ví dụ: “Tài liệu hiện có chưa nói đủ về phần này…”), rồi mới đưa ra câu trả lời "
    "tốt nhất dựa trên kiến thức chung.\n"
    "- Nếu các đoạn ngữ cảnh MÂU THUẪN nhau: nêu rõ cả hai và nói rằng chúng mâu thuẫn, "
    "không tự chọn một bên.\n"
    "\n"
    "ĐƯỢC PHÉP MỞ RỘNG\n"
    "- Với câu hỏi vượt ngoài ngữ cảnh, bạn ĐƯỢC PHÉP dùng kiến thức chung.\n"
    "- Trả lời như một kỹ sư/chuyên gia nhiều kinh nghiệm: gợi ý best practice, "
    "đánh đổi (trade-off), tình huống thực tế.\n"
    "- LUÔN tách bạch hai phần bằng nhãn:\n"
    "  [Từ tài liệu]: thông tin lấy từ ngữ cảnh được cung cấp\n"
    "  [Mở rộng]: suy luận, best practice hoặc kiến thức chung của bạn\n"
    "\n"
    "CHẤT LƯỢNG\n"
    "- Cụ thể, không chung chung. Ưu tiên lời khuyên hành động được hơn lý thuyết.\n"
    "- Khi phù hợp, kèm ví dụ (code/luồng/tình huống), ưu–nhược điểm, lỗi thường gặp.\n"
    "\n"
    "CHỐNG BỊA ĐẶT\n"
    "- TUYỆT ĐỐI không bịa dữ kiện rồi gán cho tài liệu. Không bịa deadline, "
    "người phụ trách, tên môn hay số liệu.\n"
    "- Nếu không chắc, nói: “Tài liệu không nêu rõ điều này, nhưng theo kiến thức chung…”.\n"
    "- Mở rộng bằng lập luận thì được; bịa dữ liệu thì không.\n"
    "\n"
    "Trích dẫn nguồn theo số thứ tự đoạn, ví dụ [1]. Trả lời bằng tiếng Việt."
)

_client = None


def build_client():
    """Construct the OpenAI client. Separate from the cache so tests can call it."""
    from openai import OpenAI  # imported lazily so the app starts without a key

    kwargs: dict[str, Any] = {
        "api_key": config.OPENAI_API_KEY,
        "timeout": config.OPENAI_TIMEOUT,
    }
    if config.OPENAI_BASE_URL:  # omit entirely so the SDK default applies
        kwargs["base_url"] = config.OPENAI_BASE_URL
    return OpenAI(**kwargs)


def _get_client():
    global _client
    if _client is None:
        _client = build_client()
    return _client


def reset_client() -> None:
    """Drop the cached client (used by tests that change configuration)."""
    global _client
    _client = None


def configured() -> bool:
    return bool(config.OPENAI_API_KEY)


def models() -> list[str]:
    """Primary first, then the secondary if one is configured and differs."""
    chain = [config.OPENAI_MODEL_1]
    if config.OPENAI_MODEL_2 and config.OPENAI_MODEL_2 != config.OPENAI_MODEL_1:
        chain.append(config.OPENAI_MODEL_2)
    return [m for m in chain if m]


def _format_context(chunks: list[dict[str, Any]]) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, 1):
        title = chunk.get("title") or chunk.get("id")
        blocks.append(f"[{i}] {title}\n{chunk['content']}")
    return "\n\n".join(blocks)


def _fallback(question: str, chunks: list[dict[str, Any]], warning: str) -> dict[str, Any]:
    if chunks:
        answer = (
            "Chưa tạo được câu trả lời bằng AI. Dưới đây là các đoạn tài liệu "
            f"liên quan nhất tới câu hỏi “{question}”:\n\n" + _format_context(chunks)
        )
    else:
        answer = "Không tìm thấy đoạn tài liệu nào liên quan tới câu hỏi này."
    return {"answer": answer, "mode": "fallback", "warning": warning, "model": None}


def generate_answer(question: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if not configured():
        return _fallback(
            question, chunks,
            "Chưa cấu hình OPENAI_API_KEY — đây là kết quả truy xuất, không phải câu trả lời do AI tạo.",
        )
    if not chunks:
        return _fallback(question, chunks, "Không có ngữ cảnh nào được truy xuất.")

    user_content = (
        f"Ngữ cảnh:\n\n{_format_context(chunks)}\n\n"
        f"Câu hỏi: {question}\n\n"
        "Trả lời chỉ dựa trên ngữ cảnh trên."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # Try MODEL_1, then MODEL_2. Any API failure degrades to fallback — never a 500.
    errors: list[str] = []
    for model in models():
        try:
            response = _get_client().chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=config.OPENAI_MAX_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001 - readable message, keep serving
            log.warning("openai call failed on %s: %s: %s", model, type(exc).__name__, exc)
            errors.append(f"{model}: {type(exc).__name__}")
            continue

        choice = response.choices[0] if response.choices else None
        text = (choice.message.content or "").strip() if choice else ""
        if not text:
            log.warning("openai returned empty content on %s (finish=%s)",
                        model, getattr(choice, "finish_reason", None))
            errors.append(f"{model}: empty response")
            continue

        return {"answer": text, "mode": "ai", "warning": "", "model": response.model or model}

    return _fallback(question, chunks, "Gọi AI lỗi (" + "; ".join(errors) + "); đã chuyển sang kết quả truy xuất.")
