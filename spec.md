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

> ⚠️ Phần này là **nghiên cứu của team** — dưới đây là mô tả sản phẩm theo hiểu biết chung, team phải tự
> dùng thử và xác nhận/sửa trước CP4, không được nộp nguyên văn.

- **Todoist / Google Tasks**: nhập task nhanh bằng ngôn ngữ tự nhiên, có parse ngày giờ.
  *Đáng học*: ô nhập một dòng, đoán deadline rồi cho người dùng sửa. *Đáng né*: không hiểu bối cảnh
  nhóm/môn học. *StudyFlow khác*: gắn task với gate/mốc chương trình và giải thích vì sao xếp trước.
- **Trello / Notion**: bảng cộng tác nhóm, tuỳ biến cao.
  *Đáng học*: nhìn được việc của cả nhóm. *Đáng né*: phải tự dựng và tự bảo trì cấu trúc; không tự nhắc.
  *StudyFlow khác*: rule engine tự xếp ưu tiên và nêu lý do, không bắt người dùng tự sắp.
- `[Sản phẩm 3 — team bổ sung sau khi dùng thử]`

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
- **Golden set:** `eval/golden-set.json` — **22 case**, mỗi case ghi `grounded_in` trỏ tới nguồn thật
  (10 case bám chunk trong `output/rag_chunks.jsonl`, 4 case bám view trong `ssot/ssot.db`,
  1 case bám hành vi có thật trong chatlog, 7 case dựng để kiểm thử).
  ⚠️ **Chưa đạt yêu cầu “≥10 case từ chatlog thật”.** Lý do đã kiểm chứng: chatlog trong data pack là log
  gia sư **nội dung bài giảng** (1261 lượt học viên hỏi về slide), không phải log hỏi deadline/tiến độ —
  chỉ 16 dòng chứa từ khoá tiến độ và đều là trích nội dung slide. Team cần quyết định: đổi tiêu chí này,
  hay thu thập log hỏi-đáp tiến độ thật từ Discord.
- **Quality bar:** `[CẦN TEAM CHỐT]`. Đề xuất dựa trên số đo thật hiện tại: **≥90% case qua toàn bộ tiêu chí,
  và 100% case thiếu căn cứ không bịa deadline/assignee.** (Bộ eval tự động đang đạt 34/36 = 94%.)
- **Kết quả đo thật (cập nhật lần chạy gần nhất):**
  - Unit test rule engine + schema: **19/19 pass** (`python3 agent/test_agent.py`).
  - Bộ eval hệ thống: **34/36 pass**, 1 lỗi chặn (`python3 -m agent.evals.run_evals`).
  - Lỗi còn lại **EV-NEG-004**: corpus có hai ngày Demo Day mâu thuẫn (03–05/09 ở calendar vs 01/09 ở
    timeline); cả hai chunk đều được truy xuất nhưng câu trả lời chỉ nêu một mốc, chưa nói rõ là mâu thuẫn.
  - Đã chứng minh **không bịa**: câu hỏi ngoài phạm vi bị từ chối, không sinh số liệu (EV-NEG-005 pass).
  - Đây **là** kết quả eval tự động, **chưa phải** kết quả chấm tay golden set 22 case.

## §8. Phân công & kế hoạch

- Xem bảng có tên trong `README.md`; team phải thay placeholder.
- **Willing users ≥3 tên:** Bùi Hoàng Vương, Đặng Tiến Thành, Phạm Xuân Phong.
- **Validation:** ≥5 người ngoài nhóm, giao task không hướng dẫn; log tại `validation/feedback-log.md`.
- **Multi-prototype:** So sánh form AI tự điền và 3 lựa chọn task; tối ưu hóa khả năng người dùng điều chỉnh trước khi lưu.

## §9. Changelog

| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
| 2026-07-30 | Dựng Mock flow nhập task → AI draft → rule priority → reminder preview | Chốt một luồng demo hẹp, bám mô tả ban đầu |
| 2026-07-30 | Dựng SSOT SQLite (20 user / 5 team / 100 project / 90 task) làm nguồn sự thật | Rule engine cần dữ liệu tra được, không đọc từ RAG |
| 2026-07-30 | Tách rule engine ưu tiên thành `agent/priority.py`, 7 luật, có `reason` | Yêu cầu §7: xếp ưu tiên phải giải thích được, không do LLM tự nghĩ |
| 2026-07-30 | Dựng RAG (Chroma + 36 chunk) chỉ dùng cho tra quy định | Tách nguồn: task từ SSOT, quy định từ tài liệu |
| 2026-07-31 | Thêm đăng nhập theo từng tài khoản + cá nhân hoá dashboard | Mỗi học viên phải thấy việc của chính mình |
| 2026-07-31 | Bộ eval 36 case tự động (`agent/evals/`) | Cần đo lặp lại được, không chấm cảm tính |
| 2026-07-31 | Sửa lỗi lệch múi giờ: agent so UTC với giờ máy (UTC+7) | Eval EV-DAILY-004 phát hiện; “đến hạn hôm nay” bị lệch 1 ngày |
| `[ ]` | `[Thay đổi sau user test — CHƯA CHẠY]` | `[Trỏ về feedback cụ thể]` |
