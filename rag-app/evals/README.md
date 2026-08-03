# Bộ test cho RAG chatbot

Kiểm thử endpoint `POST /api/query` của `rag-app` trên corpus Cohort 3
(36 chunk trong `output/rag_chunks.jsonl`).

Khác với `agent/evals/` — bộ đó chấm **agent tiến độ** đọc SQLite SSOT; bộ này chấm
**chatbot RAG** trả lời câu hỏi về quy chế chương trình.

## Hai file, hai vai trò

| File | Vai trò |
|---|---|
| `cases.json` | **Spec cho người đọc.** Mảng JSON thuần: `id`, `category`, `question`, `expected_answer_points`, `should_use_context`, `difficulty`, `notes`. Đưa cho reviewer hoặc import vào sheet được ngay. |
| `run_cases.py` | **Phần máy chấm được.** Mỗi case một entry trong `CHECKS`. Runner từ chối chạy nếu hai file lệch id nhau (exit 2), nên không thể có case được ghi mà không được chạy. |

## Chạy

```bash
# Khởi động backend trước
docker compose -f rag-app/docker-compose.yml up -d

python3 rag-app/evals/run_cases.py
python3 rag-app/evals/run_cases.py --only TC02
python3 rag-app/evals/run_cases.py --category adversarial
python3 rag-app/evals/run_cases.py --json /tmp/rag-report.json
python3 rag-app/evals/run_cases.py --allow-known-fail    # cho CI

RAG_BASE_URL=http://127.0.0.1:8010 python3 rag-app/evals/run_cases.py
```

Exit code `1` nếu có case FAIL, `0` nếu không. SKIP **không** làm hỏng run.

## Ba trạng thái, và vì sao SKIP không phải PASS

- `PASS` / `FAIL` — chấm được và có kết luận.
- `SKIP` — không chấm được: backend không chạy, hoặc backend đang ở `mode:"fallback"`
  (chưa cấu hình `OPENAI_API_KEY`). Ở chế độ fallback, `/api/query` chỉ trả về các
  đoạn truy xuất, không có câu trả lời do AI sinh — nên mọi assertion về **nội dung**
  câu trả lời là vô nghĩa. Các assertion chỉ về **truy xuất** vẫn chạy bình thường.
- `XFAIL` — case nằm trong `KNOWN_FAILURES` và có cờ `--allow-known-fail`.

## Cách chấm: kiểm tra tính chất, không so khớp câu chữ

Output của LLM không tất định. Không assertion nào so bằng nguyên văn một câu trả lời.
Mỗi case chỉ hỏi ba loại câu hỏi:

| Loại | Khoá trong `CHECKS` | Chấm được ở chế độ fallback? |
|---|---|:---:|
| Có lấy đúng đoạn tài liệu không? | `retrieve_all`, `retrieve_any` | ✅ |
| Con số/tên lệnh trong tài liệu có xuất hiện đúng không? | `all`, `any_groups` | ❌ |
| Có bịa ra thứ không có trong tài liệu không? | `none`, `none_regex`, `decline` | ❌ |
| Có tách bạch phần mở rộng khỏi phần trích tài liệu không? | `extension_label` | ❌ |
| Có nêu cả hai phía khi tài liệu mâu thuẫn không? | `conflict` | ❌ |
| Có hỏi lại khi input thiếu thông tin không? | `clarifies` | ❌ |

`extension_label` bám theo `SYSTEM_PROMPT` hiện tại trong
[rag-app/backend/app/llm.py](../backend/app/llm.py) — prompt đó cho phép bot mở rộng
bằng kiến thức chung **miễn là gắn nhãn** `[Từ tài liệu]` / `[Mở rộng]`.
Nếu đổi prompt, phải xem lại `EXTENSION_MARKERS` và `DECLINE_PHRASES`.

## Phân bố 40 case

| Category | Số case | Tỷ lệ |
|---|---:|---:|
| `in_context_factual` | 14 | 35% |
| `in_context_procedural` | 7 | 17.5% |
| `edge_case` | 6 | 15% |
| `adversarial` | 5 | 12.5% |
| `out_of_context_creative` | 8 | 20% |

Ràng buộc thiết kế: `in_context_*` ≥ 50% (đạt 52.5%), `out_of_context_creative` ≥ 20%
(đạt đúng 20%). Runner in lại tỷ lệ này mỗi lần chạy, nên thêm/bớt case là thấy ngay.

## Bẫy đặc thù của corpus này

Ba case dưới đây không phải câu hỏi chung chung — chúng nhắm vào chỗ corpus
**thật sự** yếu, phát hiện khi đọc lại 36 chunk:

| Case | Bẫy |
|---|---|
| `TC022` Demo Day | Corpus có **hai ngày mâu thuẫn**: `cohort3_evening_calendar.json/chunks/1` ghi 03–05/09, còn `master_timeline.json/timeline/5` ghi Tuần 6 = 01/09/2026. Cả hai đều được truy xuất ở `top_k=5`. Bot phải nêu cả hai và nói rõ là mâu thuẫn. **Đang FAIL** — cùng lỗi với `EV-NEG-004` bên `agent/evals`. |
| `TC023` Office Hours | Corpus trích từ **ảnh lịch**, chỉ ghi sự kiện lặp lại "nhiều ngày", không có khung giờ. Bot đưa ra bất kỳ giờ cụ thể nào đều là bịa. |
| `TC027` `c3-app-042` vs `P-042` | Hai quy ước đặt tên khác nhau (Deploy URL vs GitHub repo) trùng số `042`. Dễ bị gộp làm một. |

## Lỗi đã biết

`KNOWN_FAILURES` trong `run_cases.py` liệt kê case fail vì nguyên nhân đã được theo dõi
ở chỗ khác. Chúng vẫn hiện FAIL theo mặc định — chỉ `--allow-known-fail` mới hạ xuống
XFAIL, và runner vẫn in danh sách ra cuối mỗi lần chạy. Không được xoá một case đang
fail để bộ test xanh (quy tắc `eval/README.md`).

## Thêm case mới

1. Thêm object vào `cases.json` — `expected_answer_points` phải **trích được** từ một
   chunk cụ thể, ghi ref chunk vào `notes`. Không viết kỳ vọng từ trí nhớ.
2. Thêm entry cùng id vào `CHECKS`. Thiếu bước này runner exit 2.
3. Chạy lại và kiểm tra tỷ lệ category in ở đầu output vẫn đạt ràng buộc.
