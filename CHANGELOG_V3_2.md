# KHIETTRAN Autobeat Cut V3.2 — thay đổi

## Tệp đã sửa
- `main.py` — đổi thương hiệu; thêm checkbox Auto ánh sáng/màu/cân bằng trắng và trim 2 giây; tích hợp phân tích màu theo từng nguồn trong renderer; cải thiện bản dịch giao diện.
- `autobeat_core.py` — cho phép thêm các bộ lọc màu đã phân tích vào pipeline FFmpeg; cập nhật mô tả mô-đun.
- `AutoBeatVideoEditorAI.spec` — đổi tên thư mục và executable mục tiêu.
- `BUILD_EXE_WINDOWS.bat` — cập nhật tên cấu hình build và bộ cài.
- `requirements.txt` — khai báo pytest để script build có thể chạy test.
- `README_VI.md` — hướng dẫn V3.2, giới hạn và build.
- `KHIETTRAN_Autobeat_Cut.iss` — cấu hình bộ cài với tên và phiên bản 3.2.0.

## Tệp mới
- `autobeat_ai.py` — phân tích khung hình cục bộ để đưa ra hiệu chỉnh bảo thủ; cung cấp helper cắt đầu/cuối nguồn.
- `tests/test_autobeat_ai.py` — test thống kê màu và logic trim.

## Ghi chú chính xác
Các hiệu chỉnh màu là computer-vision heuristic cục bộ, không phải mô hình neural AI đã huấn luyện và không gửi video đến dịch vụ bên ngoài. Tùy chọn trim là cắt theo thời gian, không phải phát hiện nội dung. Build Windows/installer chưa được chạy trong môi trường này.
