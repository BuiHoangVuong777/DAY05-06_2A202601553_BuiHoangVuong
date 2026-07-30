# Eval

Thư mục này sẽ chứa:

- `golden-set.json`: ≥20 case, trong đó ≥10 case phát triển từ evidence/chatlog thật và đã ẩn danh.
- `run-01.*`, `run-02.*`: output đầy đủ của từng lượt, không xoá case fail.
- `traces/ai_calls.jsonl`: trace tự sinh khi gọi Gemini; mặc định chỉ lưu hash input.

Unit test trong `codebase/tests/` chỉ kiểm code/rule engine, **không thay thế golden set AI**.

Trước khi chạy lượt đầu:

1. Team chốt định nghĩa pass/fail trong `spec.md` §7.
2. Team chốt quality bar bằng số trước hạn 23:59.
3. Hai thành viên chấm độc lập 5 case khó; nếu lệch phải sửa rubric chấm.
