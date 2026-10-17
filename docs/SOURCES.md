# Nguồn và phạm vi

Bổ sung ngày 2026-10-18 cho [so sánh Astra](ASTRA-COMPARISON.md):

- [Model card GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra).
- [Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model).
- [Reasoning models](https://developers.openai.com/api/docs/guides/reasoning).
- [Compaction](https://developers.openai.com/api/docs/guides/compaction).

Guide phân biệt thông số model, tính năng nền tảng và phần tự triển khai; không coi mọi tính năng đó là độc quyền Astra.

Đối chiếu ngày 2026-10-17. Dùng tài liệu chính thức cho hợp đồng API, không suy ra thuật toán nội bộ
từ bài đăng cộng đồng hoặc quảng cáo Astra Ultra.

- [OpenAI: Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration): phân biệt quản lý trung tâm và chuyển quyền cho chuyên gia. Project áp dụng controller trung tâm và vai trò có phạm vi nhỏ, không dùng Agents SDK.
- [Ollama: Generate a chat message](https://docs.ollama.com/api/chat): endpoint `/api/chat`, messages, stream, options, think và usage.
- [Ollama: Structured outputs](https://docs.ollama.com/capabilities/structured-outputs): JSON schema trong `format`. Project còn validate kết quả bằng Python.
- [Ollama: Linux](https://docs.ollama.com/linux): cài đặt và chạy service.
- [DeepSeek: Your first API call](https://api-docs.deepseek.com/): API tương thích, base URL và bearer key.
- [OpenRouter: Quickstart](https://openrouter.ai/docs/quickstart): endpoint và định dạng gọi tương thích.

Tên “Astra Local Pipeline” mô tả project do trợ lý tạo theo yêu cầu người dùng; không biểu thị sản phẩm,
ủy quyền hay tích hợp chính thức của OpenAI. Phần được triển khai là workflow công khai phổ biến:
decomposition, bounded role calls, evidence retrieval, review/repair, checks và checkpoints.
Không xác nhận đây là nội bộ Astra Ultra, không chuyển trọng số/khả năng model lớn sang model nhỏ.

Mức độ kiểm thử: xem `VALIDATION.md` ở thư mục gốc. API thương mại chỉ được kiểm thử qua HTTP mock
nếu chưa có key và run thực; không coi mock là bằng chứng một provider/model thương mại đang hoạt động.
