# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.

---

# Case của tôi: C-002@11, ticket nói "trễ 5 ngày", DB nói 2

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-2f05` (`reports/eval_seeded_regression.json`, hàng `E-002` seed 11, eval set `2f05716234fb`) |
| Triệu chứng | Lab 8 báo FAIL: `status resolved != denied`. Ledger ghi 20.000đ (`refund_count=1`), nhãn là 0 và `denied`. Reply trôi chảy: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." Reply khớp ledger nên `reply_amount_matches_ledger` vẫn True; lỗi nằm ở chỗ khác. Các grader fail: `pass_rate`, `refund_amount_correct`, `proposal_amount_correct`, `db_fact_kept`. |
| Bước sai đầu tiên | **Event 3 `model_override`**, payload `{"delay_days": 5}`. Đơn O-202 trong DB có `delay_days = 2`, ticket ghi "Đơn giao trễ 5 ngày". |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng (đúng claim, chỉ cho phép tool đọc). Event 2 `investigator` đọc đúng `lookup_order` của O-202 với `delay_days = 2`, nên lúc đó dữ liệu DB còn nguyên. Event 3 là lần đầu tiên một giá trị trái với DB xuất hiện. Từ đó mọi bước sau đều hệ quả: event 4 `quote` 20.000đ dựa trên 5 ngày (với 2 ngày thì quote là 0, `no_entitlement`), event 5 `refund_history` bình thường, event 6 `reply` nói đúng số đã ghi nhưng số đó sai. |
| Failure mode | **FM-03** `ticket_trust` (docs/failure_taxonomy.md) |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; event 3 `quote` là `amount_vnd = 0, reason = no_entitlement`; reply "chưa đủ điều kiện hoàn"; ledger 0; Lab 8 PASS. Hai trace giống nhau ở event 1-2 và rẽ nhánh đúng ở event 3. |
| Regression test | `src/tests/test_lab9_trace_case.py` (3 test, marker `student`, chạy trong job `eval-gate` qua `-k "lab9 and not advanced"`). `test_first_wrong_step_is_the_model_override` kiểm event 3 là `model_override {"delay_days": 5}` và event 2 còn `delay_days = 2`. `test_bad_run_is_caught_by_the_graders` kiểm `DbFactKept`, `RefundAmountCorrect`, `ProposalAmountCorrect` đều fail trên `seeded_regression`. `test_fixed_run_passes_every_grader`: cùng claim@seed trên `fixed` qua cả 4 grader. Đã thấy fail trên variant lỗi và pass trên `fixed`. |
| Chưa chắc chắn | (1) Trace chỉ cho thấy *giá trị* bị đè, không cho thấy *vì sao* agent làm vậy: MockLLM không có lý do để đọc. Ở `seeded_regression` lỗi bật vô điều kiện qua công tắc `ticket_trust`, còn swarm tham chiếu chỉ dính ở seed chia hết cho 5. (2) Event `model_override` chỉ có ở lỗi "ồn ào": biến thể `quiet_override` cùng lỗi nhưng không ghi event, nên test này (dựa vào event) sẽ không bắt nó; chỉ `pass_rate` và `refund_amount_correct` dựa vào ledger bắt được. (3) Chỉ kiểm một claim@seed; không chứng minh gate bắt mọi cách ticket đè DB. |

Bài học từ case này: đọc ledger trước reply. Reply của trial này nhất quán với ledger, nên một grader chỉ so reply với ledger (FM-08) sẽ cho qua; số tiền sai bắt nguồn từ dữ kiện đầu vào bị đè ở event 3.
