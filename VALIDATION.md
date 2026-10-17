# Kiểm chứng triển khai

Ngày chạy: 2026-10-17, trên máy người dùng Ubuntu 24.04 / Intel i5-7200U / RAM 8 GB.
Ollama 0.20.6, model `qwen3:1.7b`, các vai trò chạy tuần tự, 2 CPU thread, context 4096.

## Kiểm thử kỹ thuật — bản đầu ngày 17/10

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -q
bash -n install.sh bin/astra
python3 -m compileall -q astra
```

**27 tests đều qua** ở bản đầu trước khi thêm bộ nhớ phiên. Các tình huống được kiểm tra gồm:

- Acceptance check thật có quyền từ chối review “pass” và buộc sửa.
- Bản sửa phải được review lại; không giữ review cũ cho bản chưa được review.
- Request JSON lỗi, timeout/lỗi mạng, Ctrl+C, hết budget, resume có cộng dồn usage.
- Khóa run đang chạy và từ chối checkpoint đã bị process khác cập nhật.
- Cắt output, trích nguồn không tồn tại, reviewer thiếu nguồn được dẫn.
- Giới hạn tài liệu, hash nguồn, task không bị cắt ngầm.
- HTTP payload của Ollama và Chat Completions, token usage và chi phí chưa biết.
- Key thiếu/sai định dạng, key ghi nhầm trong config, HTTP redirect và thông báo lỗi không lộ key.

Đã chạy `bash install.sh`, `astra doctor`, `astra models` từ thư mục khác (`/tmp`),
`astra --help`, `astra prompt`, `astra export --output exports/qwen17 --model qwen3:1.7b`.
Shortcut nằm tại `~/.local/bin/astra`. Chưa tạo model alias `astra-qwen17`; Modelfile đã được xuất để người dùng tự cài khi muốn.

## Chạy thật với Ollama

### Smoke test bản cuối

```bash
astra run --task-file examples/smoke.json --mode balanced
```

- Run: `runs/20261017-234003-5899169c/`.
- Kết quả: `Kết quả: 391` — kiểm tra thủ công đúng với 17 × 23.
- Trạng thái: `model_review_passed`.
- Ba lượt: planner → draft → reviewer.
- Thời gian hoạt động: **27,6 giây** trong lần chạy này.
- Checks `391`, `Kết quả:` và nội dung không rỗng đều qua.

Đây là smoke test đơn giản, không phải bằng chứng chất lượng tổng quát hoặc dự báo tốc độ mọi tác vụ.

### Lỗi model đã quan sát trong quá trình xây dựng

- Run `runs/20261017-232858-8619582c/`: đáp án phép tính đúng nhưng reviewer tạo phê bình sai.
  Controller giữ `needs_review` thay vì bỏ qua vấn đề. Prompt review sau đó được làm rõ và bổ sung kết quả checks.
- Run `runs/20261017-233610-206d28bc/`: bài đọc tài liệu laptop, 5 lượt, 159,5 giây.
  Model bỏ trích nguồn bắt buộc và gán lợi ích GPU dù tài liệu nói inference dùng CPU.
  Reviewer cùng model bỏ sót lỗi về GPU; check thiếu `[S1]` giữ trạng thái `needs_review`.
  Sau đó sửa planner để chỉ lập hành động, coi kế hoạch là tạm thời và đưa lỗi checks vào yêu cầu sửa.

Các run lỗi được giữ nguyên để kiểm tra, không thay đổi đáp án/checks nhằm tạo kết quả đẹp.
Điều này cho thấy nhiều lượt không bảo đảm model nhỏ suy luận đúng: cần tài liệu tốt,
tests độc lập và người kiểm tra; reviewer mạnh qua API là một lựa chọn cần đánh giá riêng.

### Đọc tài liệu với bản prompt cuối

```bash
astra run --task-file examples/laptop.json --mode fast
```

- Run: `runs/20261017-234114-41b7e955/`.
- Hai lượt, **70,5 giây**, trạng thái `needs_review`.
- Model trả nhiều lựa chọn thay vì một lựa chọn theo ba mục và vẫn bỏ `[S1]` bắt buộc.
- Check trích nguồn phát hiện lỗi; fast không có vòng tự sửa nên giữ bản nháp để người dùng xem.
- Kết quả này không được tính là đáp án đạt yêu cầu. Giới hạn tuân thủ hướng dẫn của model 1.7B vẫn còn.

### Tài nguyên quan sát

Trong một run, `ollama ps` báo model khoảng **1,9 GB**, **100% CPU**, context 4096.
RAM khả dụng hệ thống khi đó khoảng **3,7 GiB**. Đây là ảnh chụp trạng thái tại một thời điểm,
không phải đo peak RAM hoặc benchmark ổn định. Máy không được cấu hình GPU inference trong project này.

## API bên ngoài

Adapter tương thích được kiểm thử bằng HTTP mock loopback. Không có request tạo đáp án
đến DeepSeek, OpenRouter hoặc API thương mại khác trong đợt kiểm thử này.
Chưa xác nhận live model ID, quota, giá hay chất lượng của provider bên ngoài.
Người dùng cần điền model/key và chạy `doctor`/smoke test như hướng dẫn trước khi dùng thực tế.

## Phạm vi còn lại

- Chưa đo benchmark so sánh với Astra Ultra hoặc với chat local trực tiếp trên bộ dữ liệu lớn.
- Chưa kiểm thử hệ điều hành ngoài Ubuntu/Linux.
- Không có agent tự chạy shell, sửa repo, web search, MCP server hoặc giao diện web.
- Prompt/Modelfile dùng lại là hướng dẫn; chỉ Python runner thực thi các vòng gọi và budgets.
- Mọi trạng thái review của model cần đọc cùng báo cáo và checks; không thay thế kiểm chứng chuyên môn.

## Bản tối ưu bộ nhớ phiên — ngày 2026-10-18

**41 tests đều qua** sau khi bổ sung session; `bash -n` và `compileall` cũng qua.
14 test mới kiểm tra contract đến mọi vai trò, snapshot không đổi khi thêm note,
resume giữ prompt cũ sau khi code prompt thay đổi, phát hiện đổi model/mode/goal,
không cắt decision/fact khi thiếu context, note có nguồn và lịch sử thay thế,
không tự nâng đáp án thành fact, giới hạn preview và tương thích run cũ.

Đã xuất bộ prompt mới vào `exports/continuity-v2/`. Đã tạo phiên làm việc thật `local-work`,
mode balanced, Qwen3 1.7B, với mục tiêu pipeline local và ràng buộc tiếng Việt/RAM 8 GB.
Gói bàn giao: `sessions/local-work/HANDOFF.md`.

### Kiểm tra nhớ dữ kiện qua hai tiến trình riêng

Phiên kiểm thử riêng `memory-check`, mode fast; dữ kiện giả do lệnh note cung cấp:
“Mã dự án là SenXanh42”, nguồn ghi rõ fixture kiểm thử.

| Run | Kết quả quan sát | Lượt | Thời gian | Trạng thái controller |
|---|---|---:|---:|---|
| `20261018-000118-fc748f64` | `SenXanh42` | 2 | 57,3s | model_review_passed |
| `20261018-000647-e6f3fd4c` | `Mã dự án là SenXanh42.` | 2 | 37,6s | model_review_passed |

Đối chiếu trực tiếp state của hai run:

- Contract hash giống nhau.
- Protocol hash giống nhau.
- Cấu hình model hash giống nhau.
- Revision bộ nhớ lần lượt 2 và 3; run thứ hai nhận thêm tham chiếu kết quả trước.
- Cả hai đều truy xuất đúng dữ kiện đã ghim mà không phải dán lại trong câu hỏi.

Giới hạn thấy rõ: lượt hai vẫn thêm lời dẫn dù task yêu cầu chỉ in mã.
Checks hiện kiểm tra mã xuất hiện, không kiểm tra toàn bộ đáp án bằng chính xác mã;
reviewer cũng không bắt được lỗi định dạng này. Vì vậy `model_review_passed` không phải chứng minh
mọi ràng buộc ngữ nghĩa/định dạng đều đã đạt. Thử nghiệm xác nhận **nạp lại dữ kiện và giữ đầu vào**,
không xác nhận tư duy hoặc câu chữ bất biến qua phiên.

Chưa đo chất lượng trên hội thoại dài hàng chục lượt hoặc so sánh với Astra Ultra.
Chưa gọi API thương mại cho bộ nhớ phiên. Việc thêm memory không tạo thêm request tóm tắt AI,
nhưng tăng lượng context gửi vào mỗi lượt và có thể tăng độ trễ/chi phí nếu dùng API.
