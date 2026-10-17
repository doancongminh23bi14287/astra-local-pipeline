# Cài trên máy khác và tích hợp AI khác bằng Terminal

## A. Mang nguyên pipeline sang máy Ubuntu/Linux khác

Cần Python 3.10+ và Ollama nếu dùng local. Từ máy hiện tại:

```bash
cd ~
tar --exclude='astra-local-pipeline/runs' --exclude='astra-local-pipeline/sessions' --exclude='astra-local-pipeline/exports' --exclude='__pycache__' --exclude='private*.json' --exclude='.env' -czf astra-local-pipeline.tar.gz astra-local-pipeline
```

Chép file nén sang máy đích, sau đó:

```bash
tar -xzf astra-local-pipeline.tar.gz -C ~
cd ~/astra-local-pipeline
python3 --version
```

Nếu chưa có Python trên Ubuntu:

```bash
sudo apt update
sudo apt install python3
```

Nếu chưa có Ollama, đọc và dùng installer chính thức:

```bash
curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh
less /tmp/ollama-install.sh
sh /tmp/ollama-install.sh
ollama pull qwen3:1.7b
```

Installer có thể cần quyền sudo. Nếu Ollama chưa chạy, mở terminal riêng chạy `ollama serve`.
Với máy hiện tại, service user đã có: `systemctl --user start ollama`.

```bash
cd ~/astra-local-pipeline
bash install.sh
export PATH="$HOME/.local/bin:$PATH"
astra doctor
astra run --task-file examples/smoke.json
```

Không cần pip install. Launcher trỏ về thư mục project nên cần giữ thư mục ở vị trí đó.
Nếu di chuyển, cài shortcut vào vị trí mới sau khi kiểm tra/gỡ symlink cũ.
Launcher/lock hiện nhắm Linux; Windows dùng WSL Ubuntu. Chưa kiểm thử native Windows/macOS.

## B. Thêm model Ollama bất kỳ

```bash
ollama list
ollama pull qwen2.5:3b
astra run "Viết một email xin nghỉ phép ngắn bằng tiếng Việt." --model qwen2.5:3b --mode fast
```

Muốn mỗi vai trò dùng model khác, tạo config:

```json
{
  "roles": {
    "planner": {"provider": "local", "model": "qwen3:1.7b"},
    "worker": {"provider": "local", "model": "qwen3:1.7b"},
    "reviewer": {"provider": "local", "model": "qwen2.5:3b"}
  },
  "limits": {"keep_alive": "0s"}
}
```

```bash
astra run "Yêu cầu của bạn" --config /duong/dan/config.json
```

Dùng `keep_alive: "0s"` khi đổi giữa model lớn để giải phóng RAM sau mỗi lượt;
đổi lại sẽ nạp model lại, chậm hơn. Mặc định cùng một model nên `2m` nhanh hơn.
Không dùng model embedding/vision-only làm vai trò chat. Khả năng JSON cần kiểm tra với model cụ thể.

## C. API tương thích OpenAI Chat Completions

Runner gọi `BASE_URL/chat/completions`, gửi `model`, `messages`, `max_tokens`,
`stream: false`, và `response_format: {"type":"json_object"}` cho các bước JSON.
Không sử dụng SDK OpenAI, OAuth Codex hoặc API riêng Messages/Responses.

| Dịch vụ | `base_url` mẫu | Lưu ý |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | Chọn ID chat model hiện có trong tài khoản |
| OpenRouter | `https://openrouter.ai/api/v1` | ID thường có namespace provider; kiểm tra khả năng JSON |
| Server local có API tương thích | `http://127.0.0.1:1234/v1` | Dùng cổng thực của ứng dụng; không mặc định server đã cài |
| Provider khác | URL tương thích được provider công bố | Kiểm tra auth, max_tokens, JSON và model ID |

Các dịch vụ yêu cầu API riêng hoặc tên tham số khác cần adapter bổ sung.
Project không cam kết mọi model/nhà cung cấp đều hỗ trợ protocol này.
Giá và model thay đổi; mẫu không gắn nhãn “rẻ nhất” hoặc hard-code giá cũ.

1. Tạo tài khoản/API key tại provider bạn chọn và đặt hạn mức chi tiêu trong dashboard.
2. Copy mẫu rồi sửa model ID và endpoint:

```bash
cd ~/astra-local-pipeline
cp configs/compatible.example.json configs/private-api.json
nano configs/private-api.json
```

3. Nhập key trong terminal Bash, không dán vào file JSON hoặc câu hỏi AI:

```bash
read -rsp 'API key: ' ASTRA_API_KEY
export ASTRA_API_KEY
printf '\n'
```

Key tồn tại trong phiên shell này; terminal mới cần nhập lại. Runner không tự đọc `.env`.

4. Liệt kê model để lấy ID chính xác:

```bash
astra models --config configs/private-api.json
```

Sửa cả ba trường `roles.*.model` từ placeholder sang ID bạn chọn, rồi:

```bash
astra doctor --config configs/private-api.json
astra run "Tính 17 nhân 23, trả lời ngắn." --config configs/private-api.json --mode fast
```

`models`/`doctor` gọi endpoint danh sách, không yêu cầu tạo câu trả lời. Một số provider không
hỗ trợ danh sách model; khi đó kiểm tra ID trong dashboard, doctor có thể không xác nhận được.
Lệnh `run` gọi API thật và có thể tính phí. Đầu vào/task/tài liệu của vai trò đó được gửi đến provider.

5. Điền `input_per_million` và `output_per_million` theo USD/triệu token từ bảng giá provider
nếu muốn báo cáo ước tính. Không biết thì giữ `null`. Cache, routing, reasoning tokens và giá riêng có thể
làm hóa đơn khác ước tính. Không có API key được ghi vào báo cáo.

6. Khi dùng xong:

```bash
unset ASTRA_API_KEY
```

## D. Local làm việc, API chỉ phản biện

```bash
cp configs/hybrid.example.json configs/private-hybrid.json
nano configs/private-hybrid.json
```

Đặt `review_api.base_url` và `roles.reviewer.model` theo provider/model đã chọn; nhập key như mục C.
Giữ planner/worker là Qwen3 1.7B. Chạy:

```bash
astra doctor --config configs/private-hybrid.json
astra run --task-file examples/laptop.json --config configs/private-hybrid.json
```

Trong balanced, thường có một hoặc hai lượt API review; local thực hiện các bước còn lại.
Nếu JSON review hỏng, có thể thêm request sửa định dạng nhưng vẫn bị giới hạn tổng số lượt.
Reviewer nhận yêu cầu, checks, bản nháp và các đoạn nguồn vừa ngân sách — đây không còn là chế độ hoàn toàn offline.
Không dùng `--model` cùng cấu hình hybrid nếu muốn giữ reviewer API: `--model` chủ động đưa **mọi vai trò về local**.

## E. Đưa workflow cho AI terminal khác

Để giữ context qua nhiều lượt hoặc đổi AI, đọc [CONTEXT-GUIDE.md](CONTEXT-GUIDE.md).
Chuyển `sessions/TEN_PHIEN/HANDOFF.md` cùng các file được tham chiếu khi muốn tiếp tục công việc;
bản nén ở mục A cố ý không mang bộ nhớ riêng của các phiên.

Có hai mức sử dụng, khác nhau về khả năng thực thi:

### E1. Chỉ gắn bộ hướng dẫn

```bash
cd ~/astra-local-pipeline
astra export --output exports/my-agent --model qwen3:1.7b
cat exports/my-agent/AGENT_INSTRUCTIONS.md
```

Đưa nội dung vào system instructions hoặc file hướng dẫn mà AI terminal của bạn hỗ trợ.
Nếu ứng dụng đọc file hướng dẫn dự án, tạo project thử riêng rồi đặt nội dung vào file ứng dụng quy định;
không ghi đè hướng dẫn đang có. Cú pháp của host thay đổi theo ứng dụng/phiên bản; xem docs của host.
Prompt này không cung cấp shell, không tự tạo loop nhiều lần gọi, không cấp quyền chạy terminal.

Với Ollama, có thể gắn trực tiếp bằng Modelfile:

```bash
ollama create astra-qwen17 -f exports/my-agent/Modelfile
ollama run astra-qwen17 --think=false
```

### E2. Để AI terminal gọi pipeline thật

Host AI cần có công cụ terminal được bạn cho phép dùng. Cung cấp lệnh và hợp đồng:

```text
Khi cần một vòng lập kế hoạch/phản biện có giới hạn:
1. Tạo task JSON bằng công cụ ghi file, không nối yêu cầu người dùng vào chuỗi shell.
2. Chạy /home/acm/.local/bin/astra run --task-file /duong/dan/task.json --mode balanced.
3. Đọc exit code và report.md của run; không chỉ đọc stdout.
4. Nếu exit code 2/3, báo các điểm chưa đạt; không tự coi bản nháp là kết quả đã kiểm chứng.
5. Chỉ tăng budget hoặc đổi sang API theo cấu hình/ngân sách người dùng đã chọn.
```

Trên máy khác thay `/home/acm` bằng đường dẫn home thực. Nếu tích hợp bằng Python, truyền argv,
không dùng `shell=True`:

```python
import json
import subprocess
import tempfile
from pathlib import Path

task = {"task": "Tóm tắt ưu nhược điểm của SQLite trong 3 ý."}
with tempfile.TemporaryDirectory() as directory:
    task_path = Path(directory) / "task.json"
    task_path.write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [str(Path.home() / ".local/bin/astra"), "run", "--task-file", str(task_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    print(result.stdout)
    print("Exit code:", result.returncode)
    print(result.stderr)
```

Đây là tích hợp CLI đồng bộ; chưa triển khai MCP server, HTTP gateway hoặc agent tự sửa repo.
Host có thể dùng đáp án làm đề xuất, nhưng việc áp dụng thay đổi/chạy tests do host thực hiện và báo bằng chứng thật.

## F. Đọc kết quả khi gặp lỗi

```bash
astra --help
astra run --help
astra resume --help
```

Không thấy tiến trình: kiểm tra terminal stderr. Ollama chậm: `ollama ps`, kiểm tra RAM, chọn fast.
Hết budget: đọc báo cáo rồi resume với giới hạn tổng cao hơn nếu cần.
Một model nhỏ “tự kiểm tra” vẫn có thể tự tin sai: dùng dữ liệu tham chiếu, checks độc lập và người đọc khi cần.
