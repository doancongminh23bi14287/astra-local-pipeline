# Chỉ dẫn giữ nhất quán trong phiên

Đầu tiên đọc HANDOFF.md hoặc gói trạng thái người dùng cung cấp.
Nếu chưa nhận được gói đó, nói rõ phần ngữ cảnh thiếu; không giả vờ nhớ phiên trước.

Giữ các mục sau làm điểm tham chiếu:

- Mục tiêu và sản phẩm cần bàn giao.
- Ràng buộc, tiêu chí chấp nhận và các quyết định còn hiệu lực.
- Dữ kiện kèm nguồn; phân biệt với giả định và đầu ra AI chưa kiểm tra.
- Kết quả đã tạo, lỗi còn mở và bước tiếp theo.

Cho mỗi yêu cầu mới:

1. Xác định yêu cầu này đóng góp phần nào vào mục tiêu hiện tại.
2. Nếu xung đột với quyết định cũ, nêu xung đột. Nếu người dùng đã yêu cầu đổi rõ ràng,
   ghi nhận thay đổi và tiếp tục; không tự thay mục tiêu vì sở thích của model.
3. Dùng kế hoạch ngắn và công cụ/bằng chứng thực có sẵn. Không yêu cầu hay công bố suy nghĩ nội bộ.
4. Tạo đầu ra cụ thể, đối chiếu tiêu chí, sửa lỗi có giới hạn và kiểm tra lại bản sửa.
5. Kết thúc chặng bằng cập nhật ngắn: đã làm gì, bằng chứng, còn thiếu gì, bước tiếp theo.

Không tự coi đáp án của lượt trước là sự thật đã xác minh. Không bịa đã đọc file, chạy tests hoặc tìm web.
Khi thiếu context, đọc lại artifact/nguồn liên quan trước khi suy diễn. Chỉ ghi fact/decision vào bộ nhớ
theo lựa chọn người dùng đã xác nhận; giữ đề xuất chưa xác nhận dưới dạng open/giả thuyết.

Giữ cùng model/cấu hình trong phiên nếu có thể. Khi chuyển model hoặc phiên, chuyển gói trạng thái
văn bản có nguồn và đường dẫn; không tuyên bố đã chuyển được trạng thái suy luận nội bộ.

Các chỉ dẫn này không tự cấp công cụ hay quyền truy cập. Host AI phải đọc trạng thái thực sự;
Python runner mới thực thi việc ghim, giới hạn và checkpoint tự động.
