# Giữ mục tiêu và ngữ cảnh ổn định trong một phiên AI

Mục tiêu thực tế: mỗi lượt AI nhận lại mục tiêu, ràng buộc, quyết định và bước tiếp theo đúng phiên.
Không thể bảo đảm suy luận nội bộ hoặc câu chữ không đổi. Có thể bảo đảm runner giữ nguyên các dữ liệu
đã ghim và phát hiện thay đổi cấu hình/prompt ngoài quy trình được hỗ trợ.

## 1. Phân biệt run và session

- **Run:** một yêu cầu, gồm nhiều bước planner/worker/reviewer; có checkpoint để resume.
- **Session:** một mục tiêu dài hạn, chứa nhiều run, cùng contract/model/prompt/mode.
- `astra resume` tiếp tục đúng run bị ngắt, giữ snapshot cũ.
- `astra run --session ...` mở yêu cầu mới và nạp revision bộ nhớ mới nhất.

Ví dụ: session là “xây công cụ quản lý chi tiêu”; các run là “chọn cấu trúc dữ liệu”,
“viết hàm nhập CSV”, “review hàm”, “viết hướng dẫn”. Mỗi run vẫn cần yêu cầu cụ thể.

## 2. Tạo một phiên

```bash
astra session create chi-tieu \
  --goal "Xây công cụ quản lý chi tiêu cá nhân bằng Python." \
  --constraint "Dùng SQLite, chưa triển khai cloud." \
  --constraint "Trả lời tiếng Việt, nêu bước kiểm tra." \
  --mode balanced
```

Phiên lưu vào `~/astra-local-pipeline/sessions/chi-tieu/`:

- `session.json`: mục tiêu, ràng buộc, protocol, config, ghi chú và lịch sử run.
- `HANDOFF.md`: bản bàn giao có thể đưa cho AI khác đọc.

Tên phiên dùng chữ không dấu, số, `-`, `_`. Mục tiêu tối đa 500 byte UTF-8;
tối đa 6 ràng buộc, mỗi ràng buộc 250 byte. Hãy viết ngắn hơn giới hạn, nhất là khi dùng context 4096.
Giữ một mục tiêu rõ trong mỗi session; việc hoàn toàn khác nên dùng session khác.

Nếu muốn config API/hybrid, chọn lúc tạo:

```bash
astra session create review-code \
  --goal "Review code theo tiêu chí dự án." \
  --config configs/private-hybrid.json
```

Tạo session không gọi AI. Khi chạy session API/hybrid, các dữ liệu bộ nhớ được đưa vào prompt của vai trò đó
và gửi đến provider đã cấu hình. Key vẫn đọc từ môi trường, không ghi vào bộ nhớ.

## 3. Chạy các lượt trong cùng phiên

```bash
astra run "Đề xuất schema SQLite tối giản gồm các trường cần thiết." --session chi-tieu
astra run "Nêu 3 kiểm tra cho dữ liệu CSV trước khi nhập." --session chi-tieu
astra session show chi-tieu
```

Runner tự nạp contract, các quyết định/dữ kiện đang có hiệu lực và một ít lịch sử gần nhất.
Không cần bạn copy lại nguyên hội thoại. Những phần quan trọng không được có chỉ trong một câu chat cũ;
nên chuyển thành ghi chú có xác nhận như phần tiếp theo.

Không dùng `--model`, `--config` hay mode khác để ghi đè phiên hiện có. Muốn đổi model/phương pháp,
tạo phiên mới rồi chuyển các quyết định/dữ kiện còn đúng. Các giới hạn tổng lượt/thời gian của một run
vẫn có thể tăng bằng `resume`; đó không phải thay mục tiêu hay model.

## 4. Ghi đúng loại bộ nhớ

| Loại | Dùng cho | Cách runner xử lý |
|---|---|---|
| `decision` | Lựa chọn người dùng đã chốt | Luôn ghim, không tự bỏ khi thiếu chỗ |
| `fact` | Dữ kiện do người dùng đưa vào, có nguồn | Luôn ghim; có nguồn không đồng nghĩa đã được xác minh tự động |
| `open` | Giả thuyết/câu hỏi chưa giải quyết | Có thể bỏ khỏi prompt khi hết chỗ; vẫn giữ trên đĩa |
| `next` | Việc cụ thể cần làm tiếp | Có thể bỏ khỏi prompt khi hết chỗ; vẫn giữ trên đĩa |

```bash
astra session note chi-tieu --kind decision --text "Chọn SQLite và CSV UTF-8 cho bản đầu."
astra session note chi-tieu --kind fact --text "CSV đầu vào có cột date, amount, category." --source "docs/csv-spec.md"
astra session note chi-tieu --kind open --text "Chưa chốt cách xử lý hoàn tiền."
astra session note chi-tieu --kind next --text "Viết validate_row rồi kiểm tra ngày sai và số tiền trống."
```

Mỗi lệnh trả ID `N1`, `N2`, ...; mỗi ghi chú tối đa 400 byte UTF-8.
Nguồn của fact có thể là đường dẫn, URL hoặc mô tả phép kiểm tra; runner lưu nguồn, không tự truy cập/xác nhận nguồn đó.
Chỉ dùng lệnh note cho thông tin bạn muốn chốt. Runner không tự đưa câu trả lời của model vào fact/decision.

## 5. Sửa thông tin mà không mất lịch sử

Ví dụ ghi chú `N1` đã cũ:

```bash
astra session note chi-tieu --kind decision \
  --text "Vẫn dùng SQLite; thêm hỗ trợ CSV có dấu BOM." \
  --supersedes N1
```

Ghi chú cũ được giữ trên đĩa nhưng ngừng đưa vào prompt. Ghi chú mới ghi rõ thay thế ID nào.
Nếu chỉ thêm một ghi chú mâu thuẫn mà không `--supersedes`, cả hai có thể còn hiệu lực;
runner không có bộ giải mâu thuẫn ngữ nghĩa hoàn hảo. Hãy đọc `session show` trước khi tiếp tục.

Muốn đổi mục tiêu hoặc ràng buộc cứng: tạo session mới, ghi lý do đổi vào ghi chú và chuyển dữ kiện cần thiết.
Không sửa trực tiếp `session.json`; kiểm tra hash sẽ báo các thay đổi ở contract/config/protocol/mode.
Hash là kiểm tra nhất quán dữ liệu, không phải chữ ký chống người cố tình chỉnh cả dữ liệu và hash.

## 6. Khi hết context

Runner dùng thứ tự bỏ dữ liệu phụ:

1. Lượt chạy cũ nhất trong ba lượt gần đây được cân nhắc.
2. Ghi chú open/next cũ.
3. Kế hoạch phụ.
4. Đoạn tài liệu ít ưu tiên.

**Mục tiêu, ràng buộc, decision/fact, task hiện tại và draft cần review luôn được giữ**;
nếu vẫn quá ngân sách, dừng trước request và báo lỗi thay vì cắt ngầm. Phần bị bỏ được ghi ở
`state.json → calls → omitted`. Những phần đó vẫn nằm trong session/source/run trên đĩa.

Khi bộ nhớ ghim quá dài, hợp nhất vài ghi chú trùng bằng câu ngắn rồi dùng `--supersedes` rõ ràng;
hoặc tạo session mới với context lớn hơn và chỉ mang thông tin còn cần. Không tiếp tục nhét toàn bộ transcript.
Ưu tiên tối đa vài fact/decision quan trọng cho laptop này.

Lịch sử model chỉ mang bản xem trước đáp án, tối đa 600 byte UTF-8 mỗi run, kèm trạng thái
và cờ đã cắt. Nó nằm trong `recent_runs_unverified`; có thể bị loại khỏi prompt.
Code dài, con số quan trọng và tài liệu cần xem nguyên bản qua file:

```bash
astra run "Review đoạn code này theo mục tiêu phiên." \
  --session chi-tieu \
  --context /duong/dan/run-cu/answer.md
```

`HANDOFF.md` dẫn tới các báo cáo để người/host AI mở lại. Có file trên ổ đĩa không có nghĩa model đã đọc file đó.

## 7. Đổi terminal, khởi động lại hoặc chuyển sang AI khác

Trước khi dừng, ghi `next` và `open`, cùng file kết quả quan trọng. Terminal mới:

```bash
astra session show chi-tieu
astra run "Tiếp tục: viết validate_row theo quyết định đã chốt." --session chi-tieu
```

Nếu run trước bị ngắt, dùng đường dẫn run thay vì tạo run mới:

```bash
astra resume ~/astra-local-pipeline/runs/TEN_RUN
```

Resume giữ snapshot bộ nhớ tại lúc bắt đầu run. Ghi chú mới chỉ vào **run mới** để không đổi yêu cầu giữa chừng.
Nếu cập nhật HANDOFF bị lỗi khóa phiên, run vẫn có báo cáo; gọi `resume` run đã hoàn tất để thử ghi lại liên kết.

Với AI terminal khác:

```bash
cat ~/astra-local-pipeline/sessions/chi-tieu/HANDOFF.md
cat ~/astra-local-pipeline/templates/CONTINUITY-PROMPT.md
```

Đưa hai nội dung cho AI đọc hoặc yêu cầu host AI mở đúng hai file đó. Nếu host không có công cụ đọc file,
bạn cần dán nội dung. Đừng chỉ nói “hãy nhớ cuộc nói chuyện trước” khi model mới chưa nhận trạng thái.
Mẫu ghi tay ở `templates/SESSION-HANDOFF.md` phù hợp nếu bạn không chạy Python runner.

## 8. Quy tắc giữ cách làm việc ổn định

- Giữ một mục tiêu, một tiêu chuẩn đầu ra, một mode và cùng model ID trong phiên.
- Dùng cùng quy trình ngắn: xác định → dữ kiện → kế hoạch → tạo → kiểm tra → sửa có giới hạn.
- Khi điều chỉnh, ghi quyết định mới cùng lý do, nguồn và điều bị thay thế.
- Tách dữ kiện, giả định và đề xuất. “AI nói vậy” không đủ để thành fact đã xác minh.
- Chia nhiệm vụ nhỏ; dùng artifact và checks thay vì yêu cầu suy nghĩ càng dài càng tốt.
- Khi đổi hướng, chỉ rõ phần đổi và phần còn giữ. Không tự đổi kiến trúc vì model thích cách khác.
- Đọc lại các điểm ghim sau mỗi chặng lớn, trước khi đổi AI hoặc khi câu trả lời bắt đầu lệch mục tiêu.

Prompt/schema và config được chụp vào phiên. Nâng cấp file prompt của project không làm session cũ
tự đổi prompt; tạo session mới để dùng bộ prompt mới. Run cũ được tạo trước tính năng này chưa có snapshot prompt:
resume sẽ cảnh báo đang dùng prompt hiện tại, không thể hứa khôi phục prompt lịch sử chưa từng được lưu.

Model ID cố định chưa ghim được trọng số phía server: một tag có thể được nhà cung cấp cập nhật.
Không pull/update model giữa phiên nếu muốn giảm biến động. Giữ temperature thấp chỉ giảm ngẫu nhiên;
không đảm bảo suy luận hay đáp án bất biến. Runner không đọc/giữ chuỗi suy nghĩ nội bộ của model.

## 9. Tự kiểm tra khả năng nhớ

Test đơn giản, dùng dữ kiện giả để không nhầm với kiến thức model đã học:

```bash
cd ~/astra-local-pipeline
astra session create memory-demo --goal "Ghi nhớ mã dự án qua nhiều lượt." --mode fast
astra session note memory-demo --kind fact --text "Mã dự án là SenXanh42." --source "Fixture kiểm thử, không phải dữ kiện thực"
astra run --session memory-demo --task-file examples/memory-recall.json
```

Mở terminal khác và chạy:

```bash
cd ~/astra-local-pipeline
astra run --session memory-demo --task-file examples/memory-followup.json
```

Kiểm tra đáp án có mã đúng và `memory.json` của hai run có cùng contract/protocol.
Đây là test nhớ dữ kiện được cấp lại, không phải bằng chứng model “nhớ tự nhiên” hoặc luôn nhất quán.
Không dùng verdict tự chấm của AI làm bằng chứng duy nhất; đối chiếu với fixture và dữ kiện thật.
