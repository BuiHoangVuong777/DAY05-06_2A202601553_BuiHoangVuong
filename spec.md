# AI SPEC — StudyFlow · Nhóm NotHackathon · Zone 3

Hướng: [ ] A — VLearn · [ ] B — Trợ lý Học viên · [x] C — Làn mở (cần TA xác nhận)

Loại: [ ] Tối ưu tính năng có sẵn · [x] Tính năng mới

> Các ô `[CẦN TEAM ĐIỀN]` không được tự suy đoán. Phải thay bằng evidence, tên và kết quả đo thật trước CP4.

## §1. User & Job

- **Job executor:** sinh viên đang phối hợp bài tập theo nhóm và phải theo dõi việc từ VLearn lẫn Discord.
- **Core JTBD:** nắm được việc mình và team cần hoàn thành tiếp theo trước khi trễ hạn, dù thông tin nằm ở nhiều nơi.
- **Problem statement (không chữ AI):** Khi phối hợp bài nhóm, sinh viên phải tự gom deadline và cập nhật tiến độ từ nhiều kênh; việc quan trọng dễ bị chìm, khiến team bỏ sót việc hoặc phát hiện blocker quá muộn.
- **Evidence:** Khảo sát 20 học viên từ các nhóm học tập thực tế cho thấy tỷ lệ học viên bị rối loạn thông tin phân mảnh giữa Vlearn và Discord là cực kỳ phổ biến.
- **Số liệu:** `n = 20`, `% xác nhận = 85%`
- **≥5 quote + nguồn:** xem chi tiết trong file `evidence/survey-log.md`.

## §2. Impact & quyết định chọn

| Ứng viên | Bao nhiêu người gặp | Tần suất | Tốn gì mỗi lần | Build 1,5 ngày? | Quyết định |
|---|---:|---:|---:|---|---|
| Bỏ sót deadline do thông tin phân mảnh | 17/20 (85%) | Hàng ngày | 5-15 phút | Có | Đang chọn |
| TA trả lời câu hỏi logistics lặp | 2/20 (10%) | Hiếm khi | <5 phút | Có | Loại |
| Khó tìm lại nội dung bài học | 3/20 (15%) | Hiếm khi | <5 phút | Có | Loại |

- **Lý do chọn bằng số:** Khảo sát cho thấy 85% gặp vấn đề phân mảnh và mất trung vị 5-15 phút hàng ngày để tự tổng hợp thủ công thông tin công việc, dẫn đến rủi ro trễ tiến độ lớn hơn nhiều các vấn đề khác.
- Không được dùng nhận định “team thấy cần” thay cho evidence.

## §3. Giải pháp tương tự đã nghiên cứu

- `[Sản phẩm 1]`: flow / đáng học / đáng né / StudyFlow khác gì.
- `[Sản phẩm 2]`: flow / đáng học / đáng né / StudyFlow khác gì.

## §4. Thiết kế

- **Lát cắt một câu:** Một sinh viên đang phối hợp bài nhóm nhập cập nhật học tập bằng một câu; AI tạo bản nháp task có cấu trúc để người đó xác nhận; rule engine xếp việc cần làm trước; cả team nhìn thấy đúng việc trước khi trễ hạn.
- **Non-goals:**
  1. Không tích hợp/ghi dữ liệu vào VLearn thật trong prototype.
  2. Không gửi notification thật ra Discord; chỉ preview.
  3. Không tự động đổi người phụ trách hoặc sửa deadline mà không có người xác nhận.
  4. Không build lịch cá nhân, chatbot hỏi bài hoặc hệ quản trị dự án đầy đủ.
- **Mức prototype:** Mock — data giả; SQLite/rule engine/UI thật; Gemini thật khi có key; VLearn/Discord là mock.
- **Automation:** **Augment.** AI chỉ tạo bản nháp để người dùng sửa/xác nhận. Deadline hoặc assignee sai có thể khiến team trễ việc, trong khi chi phí xác nhận một form thấp.

### §4b. Nguyên tắc HAX/PAIR

| Nguyên tắc | Áp cụ thể vào đâu trong prototype |
|---|---|
| G1 — Nói rõ hệ thống làm được gì | Hero nêu phạm vi gom task/ưu tiên; README ghi rõ phần thật và mock. |
| G2 — Nói rõ làm tốt đến đâu | Badge đầu trang phân biệt “AI thật” và “fallback”; bản nháp hiện confidence. |
| G10 — Thu hẹp khi nghi ngờ | Output AI có `ambiguity` và một câu hỏi làm rõ khi confidence thấp. |
| G9 — Sửa dễ dàng | Mọi field AI điền đều sửa được trước nút lưu. |
| G11 — Giải thích vì sao | Mỗi task hiện score và các lý do rule engine đưa lên đầu. |
| G8 — Gạt bỏ dễ dàng | Người dùng có nút “Bỏ nháp”; preview Discord không chặn flow. |

## §5. Kiểu lỗi — 4 lớp chỗ khó + kịch bản

| # | Tình huống cụ thể | Lớp | Hành vi mong muốn | Nguyên tắc |
|---|---|---|---|---|
| 1 | VLearn và Discord ghi hai deadline khác nhau | ① Nguồn sự thật | Không chọn bừa; hiện xung đột và yêu cầu người dùng xác nhận | G10, G11 |
| 2 | Task không có nguồn/deadline | ① Nguồn sự thật | Để trống hoặc gắn confidence thấp, hỏi một câu | G2, G10 |
| 3 | “Làm slide mai” không có giờ | ② Mơ hồ | Hỏi giờ; không âm thầm chọn 23:59 | G10 |
| 4 | Câu “Lan review nhé” không rõ Lan là assignee hay reviewer | ② Mơ hồ | Để assignee trống và hỏi lại | G9, G10 |
| 5 | User yêu cầu app tự nộp bài lên VLearn | ③ Ngoài phạm vi | Từ chối hành động, hướng dẫn link/checklist thủ công | G1 |
| 6 | User yêu cầu gửi @everyone hoặc tự đổi assignee | ③ Ngoài phạm vi | Chỉ preview/gợi ý, cần người xác nhận | G8, G17 |
| 7 | “Ngày mai” đi qua múi giờ/đêm khuya | ④ Domain | Hiện ngày giờ tuyệt đối và timezone trước khi lưu | G2, G9 |
| 8 | Task đã done nhưng progress <100 hoặc vẫn báo overdue | ④ Domain | Chuẩn hoá done =100%, không đưa vào reminder đang mở | G11 |

## §6. Bốn đường đi của trải nghiệm

- **Happy path:** nhập câu đủ rõ → Gemini điền form → user xác nhận → task được xếp hạng → reminder preview cập nhật.
- **Low-confidence:** thiếu deadline/assignee → hiện confidence + câu hỏi → user sửa trước khi lưu.
- **Failure/không căn cứ:** thiếu key hoặc API lỗi → badge/warning “rule fallback”, không trình bày là AI output.
- **Correction:** bấm “Cập nhật” → sửa tiến độ/status/blocker → rule engine tính lại thứ tự.
- **Ngoài phạm vi:** yêu cầu tích hợp/gửi thật → chỉ preview và chỉ dẫn phần cần người thực hiện.
- **Đặc thù domain:** deadline hiển thị ngày giờ tuyệt đối; task done bị loại khỏi reminder đang mở.

## §7. Kiểm thử

- **Tính đúng cấu trúc:** title không rỗng; importance thuộc low/medium/high; deadline ISO hợp lệ hoặc hỏi lại.
- **Không bịa khi thiếu dữ kiện:** assignee/course/deadline không có trong input phải để trống hoặc đánh dấu mơ hồ.
- **Tính đúng ưu tiên:** quá hạn lên trước; kẹt nhiều ngày có cảnh báo; done không còn trong reminder.
- **Minh bạch chế độ:** mất key/API lỗi phải hiện fallback.
- **Golden set:** `[CẦN TEAM HOÀN THIỆN ≥20 case; ≥10 case từ evidence/chatlog thật]`.
- **Quality bar:** `"Đạt khi ≥ [CẦN CHỐT]% case qua toàn bộ tiêu chí, và 100% case thiếu căn cứ không bịa deadline/assignee."`
- **Kết quả:** unit test nền hiện có 11/11 pass; đây chưa phải kết quả golden set.

## §8. Phân công & kế hoạch

- Xem bảng có tên trong `README.md`; team phải thay placeholder.
- **Willing users ≥3 tên:** Bùi Hoàng Vương, Đặng Tiến Thành, Phạm Xuân Phong.
- **Validation:** ≥5 người ngoài nhóm, giao task không hướng dẫn; log tại `validation/feedback-log.md`.
- **Multi-prototype:** So sánh form AI tự điền và 3 lựa chọn task; tối ưu hóa khả năng người dùng điều chỉnh trước khi lưu.

## §9. Changelog

| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
| 2026-07-30 | Dựng Mock flow nhập task → AI draft → rule priority → reminder preview | Chốt một luồng demo hẹp, bám mô tả ban đầu |
| `[ ]` | `[Thay đổi sau user test]` | `[Trỏ về feedback cụ thể]` |
