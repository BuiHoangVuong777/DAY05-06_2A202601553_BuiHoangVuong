# Validation feedback log

> **TRẠNG THÁI: CHƯA CHẠY.** Bảng dưới còn trống vì chưa có buổi thử nào với người thật.
> Không được điền hộ. Quy tắc của chính repo (`evidence/survey-log.md`): *“Không điền hộ người
> trả lời và không tạo quote giả.”* Quote bịa ra làm hỏng toàn bộ giá trị phần validation và là
> gian lận trong bài nộp có chấm điểm.

Giao task: “Hãy nhập một việc học/bài nhóm và tìm xem team nên làm việc gì trước.” Người quan sát im lặng, không chỉ nút.

| # | Người thử (tên/vai) | Willing user từ CP1? | Task được giao | Quan sát hành vi/kẹt | Quote nguyên văn | Mức nghiêm trọng |
|---:|---|:---:|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

## Ba câu hỏi sau khi thử

1. Điều gì khó hiểu hoặc khó chịu nhất?
2. Kết quả này bạn có tin không — vì sao?
3. Bạn có dùng thật không — vì sao / vì sao chưa?

## Tổng hợp

- Chủ đề lặp nhiều nhất:
- Thay đổi làm trước demo:
- Điều giữ nguyên và lý do:
- Đưa vào backlog:
- Dòng changelog tương ứng trong `spec.md` §9:

---

# Hướng dẫn chạy buổi thử (đã chuẩn bị sẵn — chỉ việc làm theo)

## Chuẩn bị (5 phút, làm một lần)

```bash
# 1. Dịch vụ RAG (trợ lý trong dashboard)
docker compose -f rag-app/docker-compose.yml up -d

# 2. App VLearn có đăng nhập
cd codebase && SSOT_DB_PATH=../ssot/ssot.db ./venv/bin/python server.py
```

Mở <http://127.0.0.1:8000>. Mỗi người thử dùng **một tài khoản riêng** để thấy dữ liệu khác nhau
(danh sách trong `codebase/users_seed.json`, mật khẩu theo mẫu `<username>@vlearn2026`):

| Người thử | Tài khoản gợi ý | Sẽ thấy |
|---|---|---|
| 1 | `vuongbh` | Trưởng nhóm, 6 việc mở, 3 quá hạn, 3 bị chặn → rủi ro cao |
| 2 | `phongpx` | Thành viên, 3 việc mở, 0 quá hạn → rủi ro thấp |
| 3 | `hungcv` | Trưởng nhóm Team Echo |
| 4 | `thanhdt` | Thành viên, 3 việc quá hạn |
| 5 | `hant` | Thành viên, 0 quá hạn |

## Cách chạy (10–12 phút/người)

1. **Không hướng dẫn trước.** Đưa đúng một câu: *“Hãy tìm xem hôm nay bạn nên làm việc gì trước.”*
2. **Im lặng quan sát.** Không chỉ nút. Bấm giờ tới lúc họ nói được việc ưu tiên số 1.
3. **Ghi nguyên văn.** Chép đúng chữ họ nói, kể cả câu chê hoặc câu không xác nhận pain.
4. Hỏi ba câu ở trên, ghi nguyên văn.
5. Chấm mức nghiêm trọng: `cao` (không làm được việc) · `trung bình` (làm được nhưng khó) · `thấp` (góp ý).

## Bốn điểm cần quan sát kỹ

Đây là chỗ hệ thống **đã biết là yếu**, nên đáng kiểm chứng bằng người thật:

| Điểm | Vì sao đáng quan sát |
|---|---|
| Người dùng có hiểu **lý do xếp ưu tiên** không? | Rule engine luôn trả `reason` (vd “quá hạn 4.1 ngày · kẹt 5.1 ngày · ảnh hưởng mốc Gate 2”). Chưa ai kiểm chứng câu đó có dễ hiểu không. |
| Người dùng có tin **mức rủi ro** không? | Mức rủi ro suy từ SSOT theo ngưỡng cố định; chưa ai xác nhận ngưỡng đó hợp lý. |
| Hỏi trợ lý về **Demo Day** | Corpus đang có **hai ngày mâu thuẫn** (03–05/09 vs 01/09) và trợ lý mới nêu một mốc (lỗi EV-NEG-004). Xem người dùng có bị dẫn sai không. |
| Người dùng có nhận ra dữ liệu là **demo** không? | SSOT hiện là dữ liệu seed, không phải task thật của họ. |

## Sau khi chạy đủ 5 người

1. Điền bảng trên (nguyên văn, không diễn giải lại).
2. Viết phần **Tổng hợp**.
3. Thêm dòng tương ứng vào `spec.md` §9 — thay dòng `[Thay đổi sau user test — CHƯA CHẠY]`.
4. Yêu cầu CP5: **≥5 người ngoài nhóm**, trong đó **≥2 người thuộc willing users CP1**
   (theo `spec.md` §8: Bùi Hoàng Vương, Đặng Tiến Thành, Phạm Xuân Phong).
