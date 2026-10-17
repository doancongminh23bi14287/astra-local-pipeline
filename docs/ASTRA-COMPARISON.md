# GPT Astra có gì khác, và phần nào có thể áp dụng cho model nhỏ?

Đối chiếu tài liệu chính thức trong phiên làm việc 2026-10-17/18.

Không có cơ sở để nói mọi khả năng dưới đây chỉ Astra mới có. Cần tách **model**,
**hệ thống điều phối/công cụ**, và **bộ nhớ phiên**. Các model khác có thể có những khả năng tương tự
ở mức độ khác nhau. Project này chỉ kiểm thử Qwen3 local và không benchmark toàn thị trường.

## Những gì tài liệu xác nhận

| Thành phần | GPT-6 Astra / nền tảng OpenAI | Pipeline local hiện tại |
|---|---|---|
| Khả năng xử lý nhiệm vụ | OpenAI định vị Astra cho suy luận phức tạp, code, nghiên cứu và tạo tài liệu | Model 1.7B đã bộc lộ lỗi hiểu yêu cầu và tự review trong các thử nghiệm local |
| Ngữ cảnh | Model card công bố 1.050.000 token và đầu ra tối đa 128.000 token | Đang **cấu hình** context 4096, đầu ra ngắn để vừa laptop; đây không phải giới hạn kiến trúc tối đa của Qwen3 |
| Mức suy luận | API model card liệt kê low, medium, high, xhigh, max | Các mode fast/balanced/thorough là số bước/vòng sửa của runner, không tương đương mức effort nội bộ |

Nguồn cho các thông số Astra: [model card GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra).
Các kết quả local có trong [VALIDATION.md](../VALIDATION.md).

| Thành phần hệ thống | Điều được xác nhận | Điều không nên suy ra |
|---|---|---|
| Ultra và nhiều agent | Tài liệu OpenAI liên hệ cơ chế phối hợp subagent song song với Ultra trong Codex | Không suy ra Ultra chỉ là một prompt hoặc tham số `reasoning.effort="ultra"` |
| Giữ trạng thái suy luận | Tài liệu mô tả reasoning items và phạm vi model hỗ trợ; trạng thái này không phải văn bản suy nghĩ thô để đọc | Không thể chép một bộ prompt rồi truyền nguyên trạng thái nội bộ sang Qwen3 |
| Nén context | Responses có cơ chế compaction đưa trạng thái cần thiết sang lượt sau với ít token hơn | Không phải lời hứa không bao giờ quên, và không phải tính năng độc quyền của riêng Astra |

Nguồn: [Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model),
[Reasoning models](https://developers.openai.com/api/docs/guides/reasoning),
[Compaction](https://developers.openai.com/api/docs/guides/compaction).

Lưu ý đối chiếu: phần `all_turns` trong tài liệu đã đọc nêu các họ model hỗ trợ cụ thể.
Không tự gán hỗ trợ đó cho mọi model Astra hay mọi endpoint. Runner hiện dùng Ollama/Chat Completions;
không triển khai Responses hoặc chuyển tiếp reasoning items.

## Phần không thể chuyển bằng một file hướng dẫn

- Trọng số, kiến thức đã học, quá trình huấn luyện và năng lực tổng quát của một model khác.
- Lượng tính toán và chất lượng suy luận thực tế chỉ bằng việc đặt tên mode là “Ultra”.
- Khả năng kiểm tra đúng một vấn đề mà model nền chưa hiểu. Trong thử nghiệm, reviewer cùng Qwen3 đã bỏ sót lỗi.
- Bảo đảm mọi câu trả lời nhất quán hoặc không ảo giác. Thêm nhiều lượt còn có thể củng cố lỗi ban đầu.

Tài liệu được đọc không công bố đủ chi tiết để tái dựng thuật toán nội bộ của Astra Ultra.
Không dùng lời quảng cáo “prompt bí mật” hoặc “copy tư duy” làm tiêu chuẩn kỹ thuật.

## Phần có thể triển khai cho local và model giá rẻ

| Nhu cầu | Cách thực hiện trong project | Phạm vi bảo đảm |
|---|---|---|
| Không mất mục tiêu | Contract gồm goal, constraints, method; ghim vào mọi lượt | Kiểm tra được payload luôn chứa contract; model vẫn có thể không làm đúng |
| Không đổi cách làm ngầm | Giữ bản chụp prompt/schema, cấu hình model và mode trong phiên | Các run mới cùng phiên dùng lại bản đó; backend/trọng số server không do runner kiểm soát |
| Nhớ quyết định | Ghi chú decision/fact có ID và nguồn; thay thế phải chỉ rõ ID cũ | Giữ dữ liệu đã ghi, không khẳng định dữ kiện người dùng nhập luôn đúng |
| Đổi terminal/AI | HANDOFF.md đọc được, dẫn tới file và kết quả đã tạo | AI/ứng dụng mới phải thực sự đọc file; file tồn tại chưa đủ |
| Context nhỏ | Lược lịch sử phụ trước, giữ mục tiêu và quyết định; quá tải thì báo lỗi | Không cắt ngầm phần ghim; không giữ được toàn bộ hội thoại trong 4096 token |
| Giảm sai sót | Checks bằng Python, phản biện có giới hạn, review lại bản sửa | Checks chỉ bao phủ điều đã khai báo; không phải oracle |

Đây là ổn định **quy trình và trạng thái có thể kiểm tra**, không phải cố định chuỗi suy luận nội bộ.
Nếu phát hiện bằng chứng mới, nên sửa giả định sai có ghi nhận thay vì giữ một kết luận sai cho “nhất quán”.

## Lựa chọn hợp lý cho máy của bạn

Giữ Qwen3 1.7B, một model tại một thời điểm và câu hỏi nhỏ. Ưu tiên bộ nhớ gọn cùng tiêu chí rõ
trước khi tăng số agent. Khi có API và ngân sách, có thể dùng model mạnh hơn ở reviewer;
cần đo trên nhiệm vụ thật trước khi cho rằng hiệu quả tăng. Hiện chưa có đánh giá API thực trong project.

Hướng dẫn thực hành: [CONTEXT-GUIDE.md](CONTEXT-GUIDE.md).
