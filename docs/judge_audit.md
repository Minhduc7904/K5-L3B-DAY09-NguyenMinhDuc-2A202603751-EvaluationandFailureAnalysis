# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (từ thư mục `src/`). FAIL là lớp dương: việc của judge là tìm lỗi.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** cả 3 | **Dùng** (kèm sửa rubric bên dưới) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Trượt** κ (0.375 < 0.6) và recall (0.3 < 0.7); precision đạt | **Loại** khỏi gate |

Ma trận nhầm lẫn (người × judge):

| | tp | fp | fn | tn | Tỉ lệ FAIL quan sát | Tỉ lệ FAIL sau Rogan-Gladen |
|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

## Vì sao không dùng `helpful` làm gate

1. **Precision = 1.0 không cứu được nó.** Judge chưa bao giờ báo FAIL nhầm (fp = 0), nhưng nó bỏ sót 21/30 lỗi thật (recall 0.3). Một gate dựa vào nó sẽ cho qua 70% bản lỗi.
2. **Nó mù đúng loại lỗi nguy hiểm nhất.** Trong 30 lỗi do người gắn nhãn, judge bắt 9/9 lỗi "giọng cụt", "không hỏi lại mã đơn", "trả lời lạc đề", nhưng bắt **0/18 lỗi "sai tiền"** và 0/3 lỗi "sai xưng hô". Khi bỏ 18 ca "sai tiền" ra, recall lên 0.75 và κ lên 0.837, tức là gần như toàn bộ điểm yếu nằm ở một lớp lỗi. Judge chỉ nhìn câu trả lời, không thấy ledger, nên một câu lịch sự nói "đã hoàn 55.000đ" vẫn PASS khi ledger ghi 40.000đ. Đây chính là FM-08 trong `docs/failure_taxonomy.md`.
3. **Thiên vị độ dài và lịch sự.** Các câu trả lời dài, lặp lời xin lỗi ("LogiX thành thật xin lỗi… rất trân trọng sự kiên nhẫn…") đều được PASS dù sai tiền. Judge đang chấm văn phong, không chấm tính đúng.
4. **Tỉ lệ lỗi quan sát bị đánh giá thấp 3 lần.** Judge báo 9% FAIL, trong khi người gắn 30%. Rogan-Gladen kéo con số về 0.30 (sensitivity 0.3, specificity 1.0), nhưng việc phải sửa số bằng công thức đã cho thấy judge không dùng làm gate trực tiếp được.
5. **Tiền không do judge chấm.** Quy tắc của taxonomy: tiền và approval chấm bằng code. FM-08 sẽ có grader code riêng (trích số tiền trong reply, so với ledger) ở M3.

## ≥5 case audit thủ công

Nguồn: `data/eval/judge_tone_public.csv` (cột `note` của người gắn nhãn) và `judge_helpful_public.csv`. "Ai đúng" là nhận định của tôi sau khi đọc câu trả lời, không chỉ chép ghi chú.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú và sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | **Người** | Xưng "em" và "nha" quá suồng sã với khách; judge coi là "thân thiện". Rubric: thêm quy tắc cố định về xưng hô ("Dạ, LogiX … anh/chị"), cấm "em", "bạn", "nha", và đưa 2 ví dụ FAIL vào prompt judge. |
| 2 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | **Người** | Giọng ra lệnh ("không cần nhắn thêm"); judge chỉ bắt được "Dạ, vui lòng". Rubric: FAIL nếu có câu mệnh lệnh phủ định hướng vào khách; judge phải đánh giá cả câu, không chỉ mở đầu. |
| 3 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Câu ngắn nhưng đủ ý. Judge phạt vì "thiếu lời xin lỗi". Rubric: lời xin lỗi chỉ bắt buộc khi ticket nêu lỗi của LogiX (trễ, hỏng); không bắt buộc ở thông báo hoàn tiền thường. |
| 4 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | **Người** | "refund" nằm trong từ vựng CS LogiX cho phép. Rubric: thêm danh sách từ vay được phép (refund, ticket); chỉ phạt tiếng Anh ngoài danh sách. |
| 5 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** (theo ghi chú: người đọc nhầm ticket) | Sửa nhãn người thành FAIL. Khi sửa, tp 25, fp 3: P 0.893, R 0.806, κ 0.784 (tốt hơn). Hành động: ghi vào quy trình rằng nhãn người cũng cần kiểm lại, không phải chân lý tuyệt đối. |
| 6 | H-063 "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | **Người**, nhưng đây không phải lỗi giọng điệu | Lỗi là hứa hẹn ngoài kết quả hệ thống, thuộc về độ chính xác, không phải tone. Rubric tone không nên gánh việc này: chuyển sang kiểm tra bằng code (không được có "sẽ hoàn thêm" khi ledger không có khoản đó). |
| 7 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | **Người** | Dịch máy, mất dấu tiếng Việt. Rubric: thêm điều kiện "phải có dấu"; nên kiểm bằng code (tỉ lệ ký tự có dấu) trước khi gọi judge. |
| 8 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | Không rõ, thiên về **người** | Lặp "Dạ" do lỗi gõ không đổi giọng điệu. Rubric: lỗi chính tả vô nghĩa không phạt ở tiêu chí tone, nhưng ghi nhận ranh giới chưa rõ; cần thêm ví dụ. |
| 9 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | **Người** | Judge không thấy ledger nên không thể phát hiện. Không sửa được bằng rubric: tiền phải chấm bằng code (FM-08). |
| 10 | HL-098 (xin lỗi hai lần, nói 120.000đ, ledger 90.000đ) | PASS | FAIL | **Người** | Câu dài và nhiều lời xin lỗi làm judge PASS (thiên vị độ dài); số tiền sai vẫn lọt. Loại `helpful` khỏi gate; thêm kiểm tra số tiền bằng code. |
| 11 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | **Người** | Sai xưng hô và không có thông tin số tiền. Judge `helpful` PASS cả 3 ca "sai xưng hô". Xưng hô thuộc tiêu chí tone, nên tiêu chí này đã có judge `tone_ok` lo. |

## Kết luận
- **Tiêu chí bị loại: `helpful`.** Ma trận nhầm lẫn tp 9, fp 0, fn 21, tn 70 cho recall 0.3 và κ 0.375, đều dưới sàn. Judge không bắt được 18/18 lỗi sai tiền và 3/3 sai xưng hô. Không dùng làm gate, chỉ có thể xem như tín hiệu phụ cho giọng văn nếu được hiệu chỉnh lại.
- **Tiêu chí được dùng: `tone_ok`** (κ 0.757, P 0.857, R 0.800, đều qua sàn). Vẫn phải sửa rubric theo các ca 1–4 và 7 (xưng hô, mệnh lệnh, xin lỗi có điều kiện, từ vay, dấu tiếng Việt), rồi chạy lại calibration trên nhãn mới.
- **Việc không giao cho judge:** số tiền trong reply (FM-08), hứa hẹn ngoài hệ thống (ca 6) và dấu tiếng Việt (ca 7) có thể kiểm bằng code, nên nên làm bằng code để giảm gánh nặng và độ nhiễu của judge.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 mẫu mỗi tiêu chí); cần nhãn người mới để có held-out thật. Khoảng tin cậy của κ trên n = 100 còn rộng, và một nhãn người sai (H-081) đã làm κ lệch 0.03, nên cần ít nhất hai người gắn nhãn để đo độ đồng thuận giữa người với người.
