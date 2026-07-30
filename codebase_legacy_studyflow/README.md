# StudyFlow prototype

Prototype mức **Mock** cho luồng duy nhất:

> Sinh viên nhập task → AI tạo bản nháp có cấu trúc → sinh viên xác nhận → rule engine xếp ưu tiên và tạo nhắc việc → team nhìn thấy việc cần làm.

## Chạy trong 30 giây

Yêu cầu: Python 3.10 trở lên. Không cần cài package.

```bash
cd codebase
cp .env.example .env
python3 server.py
```

Mở <http://127.0.0.1:8000>. Lần chạy đầu tự tạo 4 task giả theo ngày hiện tại.

Để có lời gọi AI thật, điền `GEMINI_API_KEY` vào `codebase/.env`, dừng rồi chạy lại server. Không có key thì app vẫn chạy, nhưng UI và API ghi rõ kết quả là **rule fallback**.

## Chạy test

```bash
cd codebase
python3 -m unittest discover -s tests -v
```

## Phần thật và phần mock

| Thành phần | Trạng thái |
|---|---|
| Tạo/cập nhật task, SQLite | Thật |
| Xếp ưu tiên, cảnh báo quá hạn/kẹt, mục tiêu tuần | Thật — deterministic rule engine |
| Trích xuất câu nhập thành task | Gemini thật khi có key; fallback được dán nhãn khi không có key |
| Dữ liệu VLearn/Discord | Data giả |
| Tin nhắn Discord | Chỉ preview, chưa gửi ra Discord |
| Đồng bộ VLearn | Chưa build |

Gemini dùng Interactions API với `store=false`. Trace mỗi AI call được ghi vào `eval/traces/ai_calls.jsonl`; mặc định chỉ lưu hash input để giảm rủi ro dữ liệu.

## API nhanh

| Method | Endpoint | Công dụng |
|---|---|---|
| GET | `/api/health` | Trạng thái app/AI và mức prototype |
| GET | `/api/dashboard` | KPI, task đã xếp hạng, reminder preview |
| GET/POST | `/api/tasks` | Danh sách / tạo task |
| PATCH | `/api/tasks/:id` | Sửa task |
| POST | `/api/tasks/:id/check-in` | Cập nhật tiến độ và blocker |
| POST | `/api/ai/parse-task` | AI trích xuất task từ một câu |

Có thể truyền `?now=<ISO-8601>` vào dashboard/tasks để tái hiện case demo một cách kiểm chứng được.

## Cấu trúc

```text
codebase/
├── public/                 # UI không framework
├── studyflow/
│   ├── ai_service.py       # Gemini + fallback + trace
│   ├── api.py              # HTTP API/static server
│   ├── repository.py       # SQLite
│   └── rule_engine.py      # Luật ưu tiên và reminder
├── tests/
├── .env.example
└── server.py
```
