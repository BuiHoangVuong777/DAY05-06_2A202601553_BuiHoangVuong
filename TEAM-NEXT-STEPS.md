# Việc team làm tiếp theo

## 60 phút đầu — ưu tiên tuyệt đối: evidence + CP1

1. **Cả team (5 phút):** xác nhận pain statement, lát cắt một câu và Track C trong `discovery/cp1-canvas.md`.
2. **2 người evidence (35 phút):** hỏi 20 người ngoài nhóm bằng bộ câu hỏi trong `evidence/survey-log.md`; ghi nguyên văn, kể cả câu trả lời không xác nhận pain.
3. **1 người product/spec (20 phút):** từ log thật tính `n`, `% xác nhận`, tần suất, thời gian/hậu quả; điền `spec.md` §1–§2 và bảng impact 3 ứng viên.
4. **1 người code (song song, 15 phút):** chạy app, điền API key local, thử một input giả và xác nhận trace AI được tạo.
5. **1 người eval (song song):** mở rộng `eval/golden-set.json` lên ≥20 case; thay ít nhất 10 case bằng case phát triển từ evidence/chatlog thật, giữ mã nguồn và ẩn danh.

## Sau khi CP1 được TA xác nhận

- Chốt quality dimensions + quality bar trước khi chạy golden set.
- Chỉ sửa luồng hiện có; không thêm calendar, chatbot, auth hay Discord bot thật.
- Test 4 đường đi: happy, low-confidence, AI failure/fallback, correction.
- Mời trước 5 người thử CP5, trong đó ít nhất 2 người thuộc willing users CP1.

## Quy tắc Git cho team

```bash
git switch -c feat/<ten-ngan>
git add <dung-file-minh-lam>
git commit -m "feat: <mo-ta-ngan>"
```

Không commit `.env`, API key, `venv/`, database `.db` hoặc nguyên data pack. Trước khi merge, một người khác review file và người đứng tên phải giải thích được phần đó.
