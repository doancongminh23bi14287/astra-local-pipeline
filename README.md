# Astra Local Pipeline

Workflow AI nhẹ cho Ubuntu, Python 3.10+, Ollama và API tương thích Chat Completions.
Mặc định dùng **Qwen3 1.7B**, chạy tuần tự trên máy **i5-7200U / RAM 8 GB / CPU inference**.
Không cần Docker, GPU, pip hoặc framework agent lớn.

Đây là thiết kế độc lập theo yêu cầu “áp dụng cách làm việc của Astra Ultra”:
đặt tiêu chí → chia việc → tạo bản nháp → phản biện → sửa → kiểm tra lại.
Không phải mã nguồn/cơ chế suy luận nội bộ của Astra Ultra, không fine-tune model,
và chưa có bằng chứng chất lượng ngang model lớn. Mỗi vai trò là một lượt gọi có nhiệm vụ riêng;
một model nhỏ có thể đảm nhận tất cả vai trò.

## Mới: giữ ngữ cảnh qua nhiều lượt

```bash
astra session create du-an --goal "Xây công cụ Python chạy local." --constraint "Trả lời tiếng Việt."
astra session note du-an --kind decision --text "Dùng Python standard library và SQLite."
astra run "Đề xuất cấu trúc dữ liệu ngắn gọn." --session du-an
astra run "Nêu các kiểm tra cần viết cho cấu trúc đó." --session du-an
astra session show du-an
```

Mỗi phiên ghim mục tiêu, ràng buộc, mode, model/config và bộ prompt/schema.
Mỗi run chụp bộ nhớ riêng; resume không tự đổi bộ nhớ giữa chừng.
`sessions/du-an/HANDOFF.md` giúp tiếp tục ở terminal/AI khác. Các kết quả model cũ được đánh dấu chưa xác minh;
fact/decision chỉ được thêm bằng lệnh note. Phần ghim không vừa context sẽ báo lỗi, không bị cắt ngầm.

Đọc [guide chống quên context](docs/CONTEXT-GUIDE.md) và
[Astra có gì khác, phần nào có thể áp dụng cho model nhỏ](docs/ASTRA-COMPARISON.md).
Điều được giữ ổn định là đầu vào và quy trình; không có bảo đảm mọi suy luận/đáp án đều giống nhau hoặc đúng.

## 1. Cài và chạy ngay trên máy này

```bash
cd ~/astra-local-pipeline
bash install.sh
astra doctor
astra run "Giải thích sự khác nhau giữa RAM và ổ SSD trong 3 gạch đầu dòng."
```

Nếu shell chưa nhận `astra`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Lệnh tương đương, không cần cài shortcut:

```bash
cd ~/astra-local-pipeline
python3 -m astra run "Giải thích RAM trong 2 câu."
```

Lần đầu nạp model có thể chậm. Một workflow gồm nhiều lượt nên chậm hơn một câu chat thông thường.
Terminal in bước đang chạy, ví dụ `[1/7] planner`. Dùng `Ctrl+C` để lưu checkpoint và dừng.

## 2. Chọn mức xử lý

| Chế độ | Các bước | Số lượt thông thường | Phù hợp |
|---|---|---:|---|
| `fast` | Viết → kiểm tra | 2 | Câu hỏi ngắn; không tự sửa |
| `balanced` | Kế hoạch → viết → kiểm tra → tối đa 1 vòng sửa + kiểm tra lại | 3–5 | Mặc định cho máy này |
| `thorough` | Như balanced, tối đa 2 vòng sửa | 3–7 | Bài khó, chấp nhận chậm |

JSON lỗi có thể thêm tối đa một lượt sửa định dạng cho mỗi bước có cấu trúc,
nhưng vẫn tính vào giới hạn tổng `max_calls`. Model báo lỗi mạng không được tự gọi lại.

```bash
astra run "Tính 17 nhân 23, trả lời một câu." --mode fast
astra run "Lập kế hoạch học Python 7 ngày, mỗi ngày 30 phút, viết thật ngắn." --mode balanced
astra run --task-file examples/laptop.json --mode thorough
```

## 3. Dùng tài liệu riêng

```bash
astra run "Tóm tắt nội dung chính và trích nguồn [S1]." --context /duong/dan/ghi-chu.md
astra run --task-file examples/laptop.json
```

`--context` có thể lặp lại. Chỉ đọc file bạn chỉ định, dạng text UTF-8, tối đa 12 file,
256 KB/file. Pipeline chọn các đoạn gần từ khóa của yêu cầu, lưu nguồn và SHA-256.
Đây là truy xuất từ khóa đơn giản, không phải tìm kiếm ngữ nghĩa/đọc toàn bộ tài liệu.
PDF, ảnh, website cần chuyển hoặc trích thành text trước. Pipeline không tự duyệt web.

Ngữ cảnh được giới hạn để vừa model nhỏ. `state.json → calls → omitted` ghi nguồn/kế hoạch
bị bỏ khỏi từng prompt vì thiếu chỗ. Task và bản nháp để review không bị cắt ngầm;
nếu chúng quá dài, workflow báo lỗi để bạn rút gọn hoặc tăng `num_ctx`.
Nguồn có nhãn hợp lệ chưa đảm bảo kết luận được nguồn đó hỗ trợ; cần đọc review và tài liệu.

## 4. Đặt tiêu chí kiểm tra thật

Tạo một file JSON tương tự `examples/smoke.json`:

```json
{
  "task": "Tính 17 nhân 23. Chỉ trả lời một dòng dạng: Kết quả: số.",
  "checks": {
    "contains": ["391", "Kết quả:"],
    "not_contains": ["không biết"]
  }
}
```

```bash
astra run --task-file examples/smoke.json
```

Hỗ trợ `contains`, `not_contains` (không phân biệt hoa thường), `json: true`
(toàn bộ đáp án phải parse được thành JSON thuần), kiểm tra nhãn `[S1]` tồn tại và nội dung không rỗng.
Đường dẫn `context_files` tính từ thư mục chứa task JSON; `--context` tính từ terminal hiện tại.
Chọn checks theo yêu cầu thực, không chọn theo đầu ra model đã tạo. Kiểm tra chuỗi không chứng minh
đúng toán học, tính thực tế hay code chạy đúng. File code được trả trong câu trả lời;
pipeline này không tự ghi đè dự án, chạy code hoặc thực hiện lệnh do model đề xuất.

## 5. Xem kết quả và tiếp tục

Mỗi run có thư mục riêng trong `~/astra-local-pipeline/runs/`:

- `answer.md`: đáp án/bản nháp mới nhất.
- `report.md`: trạng thái, lượt gọi, thời gian, usage, chi phí ước tính, vấn đề còn lại.
- `state.json`: checkpoint, cấu hình chụp lúc chạy, prompt/response từng bước.
- `review.json`, `checks.json`, `sources.json`: phản biện và bằng chứng kiểm tra.

```bash
astra resume ~/astra-local-pipeline/runs/TEN_THU_MUC_RUN
astra resume ~/astra-local-pipeline/runs/TEN_THU_MUC_RUN --max-calls 10 --max-seconds 1200
```

Resume tiếp tục bước chưa hoàn tất, giữ nguyên lượt gọi và thời gian đã dùng.
Các giới hạn mới là **tổng**, không phải cộng thêm. Không thay provider/model giữa một run;
muốn đổi chúng hãy tạo run mới. Request bị ngắt có thể đã được provider xử lý và tính phí;
resume bước đó sẽ tạo request mới. Run đã kết thúc không chạy lại khi resume.

| Trạng thái | Exit code | Ý nghĩa |
|---|---:|---|
| `model_review_passed` | 0 | Reviewer không tìm thấy lỗi và checks đã qua; không phải chứng minh đúng |
| `needs_review` | 2 | Còn lỗi/không chắc chắn sau số vòng cho phép |
| `budget_exhausted` | 3 | Dừng vì giới hạn, giữ bản nháp nếu có |
| `failed` | 1 | Lỗi kết nối/schema/cấu hình/ngữ cảnh |
| `interrupted` | 130 | Bạn dừng bằng Ctrl+C, có thể resume |

Nội dung `answer.md` chỉ là kết quả đã duyệt khi xem cùng `report.md` và trạng thái.
Nếu gọi từ script/AI khác, stdout là đáp án; stderr là tiến trình và đường dẫn báo cáo.

## 6. Đổi model local

Hai model trên máy này đã tải. Ví dụ:

```bash
astra models
astra run "Tóm tắt lợi ích của việc sao lưu dữ liệu trong 2 câu." --model qwen3:0.6b --mode fast
astra run "Tóm tắt lợi ích của việc sao lưu dữ liệu trong 2 câu." --model qwen3:1.7b
```

Với model khác:

```bash
ollama pull qwen2.5:3b
astra run "Giải thích Python list và tuple trong 3 ý." --model qwen2.5:3b
```

Lệnh `ollama pull` tải thêm dữ liệu; chỉ chạy nếu bạn muốn model đó.
Model cần hỗ trợ chat và JSON có cấu trúc để làm planner/reviewer. Bản 0.6B nhanh nhưng
có thể hiểu sai nhiệm vụ hoặc tạo JSON kém; đây không phải nâng cấp năng lực bằng prompt.

## 7. API giá rẻ hoặc kết hợp local + API

Xem hướng dẫn đầy đủ ở [docs/INSTALL-OTHER-AI.md](docs/INSTALL-OTHER-AI.md).
Có mẫu `configs/compatible.example.json` (cả ba vai trò qua API) và
`configs/hybrid.example.json` (local lập kế hoạch/viết, API review).
Cần tự chọn model đang có trong tài khoản, kiểm tra giá và nhập API key ở terminal.
Mẫu để model ID là placeholder; không âm thầm chọn model có phí và không tự fallback ra cloud.

Các trường đơn giá để `null` cho đến khi bạn điền giá thật. Nếu thiếu giá/usage hoặc có request lỗi,
báo cáo ghi chi phí **chưa biết**, không ghi miễn phí. Giá ước tính không phải hóa đơn hay hạn mức USD cứng.
Hạn mức thanh toán cứng cần đặt ở nhà cung cấp. Local không có phí API; vẫn tiêu thụ điện/tài nguyên máy.
Khi chọn API/hybrid, task, đoạn tài liệu và bản nháp cần cho vai trò đó được gửi đến provider đã chọn.

## 8. Xuất hướng dẫn cho AI khác

```bash
astra prompt
astra export --output exports/qwen17 --model qwen3:1.7b
ollama create astra-qwen17 -f exports/qwen17/Modelfile
ollama run astra-qwen17 --think=false
```

`astra-qwen17` là model cùng trọng số được gắn system prompt, không phải model được huấn luyện lại.
Chat trực tiếp với nó chỉ áp dụng hướng dẫn trong một lượt; dùng `astra run` mới có
các lượt gọi riêng, kiểm tra định dạng, giới hạn và checkpoint được code thực thi.
Muốn dùng model đã gắn prompt trong pipeline:

```bash
astra run "Yêu cầu của bạn" --model astra-qwen17
```

`AGENT_INSTRUCTIONS.md` trong thư mục export có thể đưa vào system instructions của AI khác.
Đọc tài liệu tích hợp để phân biệt prompt, runner và quyền chạy terminal của host AI.

## 9. Chỉnh cho máy 8 GB

Mặc định một vai trò tại một thời điểm, hai CPU thread, context 4096, thinking tắt,
model giữ trong RAM 2 phút sau request. Đầu ra mặc định ngắn để giảm độ trễ.

```bash
cp configs/local.json configs/private-local.json
nano configs/private-local.json
astra run "Yêu cầu của bạn" --config configs/private-local.json
```

Muốn dài hơn: tăng `answer_tokens` lên 768 và `num_ctx` lên 8192, đóng bớt tab trình duyệt;
RAM và độ trễ sẽ tăng. Không nên mở nhiều run local đồng thời trên máy này.
Run lock chỉ ngăn hai process ghi cùng một checkpoint, không khóa mọi ứng dụng Ollama.
Giới hạn thời gian chặn lượt gọi mới; timeout mạng là socket timeout, không phải giới hạn CPU cứng.
Ngân sách input dùng số byte UTF-8 như ước lượng token bảo thủ, không có tokenizer riêng cho mọi model.

```bash
ollama ps
ollama stop qwen3:1.7b
```

`ollama stop` giải phóng model khi không còn dùng; không chạy lệnh này lúc workflow đang xử lý.

## 10. Kiểm thử và xử lý lỗi

```bash
cd ~/astra-local-pipeline
python3 -m unittest discover -s tests -v
bash -n install.sh bin/astra
```

Tests dùng model giả và HTTP server loopback để kiểm tra budgets, resume, review sau sửa,
định dạng provider, request lỗi và không lộ API key; không dùng API trả phí.
Test thực với local:

```bash
astra run --task-file examples/smoke.json
```

- Không kết nối Ollama: `systemctl --user start ollama` trên máy này. Máy khác có thể dùng system service hoặc mở `ollama serve` trong terminal riêng.
- Thiếu model: `ollama pull qwen3:1.7b` rồi `astra doctor`.
- JSON lỗi/cắt token: kiểm tra `state.json`, tăng `plan_tokens`/`review_tokens` hoặc chọn model tốt hơn.
- API HTTP 400: kiểm tra model hỗ trợ Chat Completions/JSON; đặt `json_mode` thành `none` nếu model không hỗ trợ response_format. Code vẫn validate JSON trả về.
- Task/draft quá dài: dùng tài liệu `--context`, yêu cầu gọn hơn hoặc tăng `num_ctx`.
- Không thể tự suy luận “đã đúng” từ `model_review_passed`: cùng model có thể lặp lại cùng lỗi.

Muốn gỡ shortcut: kiểm tra `readlink ~/.local/bin/astra` rồi dùng `unlink ~/.local/bin/astra`.
Dữ liệu và project vẫn nằm trong thư mục riêng; giữ thư mục nếu cần đọc lại runs.

## Tài liệu kỹ thuật

- [Kiến trúc và workflow](docs/ARCHITECTURE.md)
- [Cài trên máy khác, kết nối API và AI terminal](docs/INSTALL-OTHER-AI.md)
- [Nguồn tham khảo và phạm vi xác nhận](docs/SOURCES.md)
- [Kết quả kiểm thử thực và giới hạn đã quan sát](VALIDATION.md)
- [Giữ ngữ cảnh trong một phiên](docs/CONTEXT-GUIDE.md)
- [Mẫu hướng dẫn cho AI khác](templates/CONTINUITY-PROMPT.md)
