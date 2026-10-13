# Hướng dẫn tạo bộ cài Windows — KHIETTRAN Autobeat Cut V3.2

## Trạng thái

Mã nguồn và quy trình đóng gói đã được chuẩn bị. Bộ cài `.exe` chỉ được xem là hoàn tất sau khi workflow chạy thành công trên Windows và tạo ra `KHIETTRAN_Autobeat_Cut_Setup.exe`. Môi trường làm việc hiện tại là Linux, không có PyInstaller, PySide6 hoặc Inno Setup nên không thể xác minh trực tiếp bộ cài Windows tại đây.

## Cách lấy bộ cài từ GitHub Actions

1. Tạo repository GitHub riêng và tải toàn bộ nội dung gói mã nguồn này lên repository (bao gồm thư mục `.github/workflows`).
2. Mở tab **Actions** của repository.
3. Chọn workflow **Build KHIETTRAN Autobeat Cut installer**.
4. Nhấn **Run workflow** và chờ tất cả bước đều màu xanh.
5. Mở lần chạy thành công, phần **Artifacts**, tải `KHIETTRAN-Autobeat-Cut-Windows-Installer`.
6. Giải nén artifact để lấy `KHIETTRAN_Autobeat_Cut_Setup.exe`.

Workflow sẽ chạy unit tests, tải FFmpeg/FFprobe bản Windows, đóng gói ứng dụng bằng PyInstaller, tạo bộ cài bằng Inno Setup và lưu bộ cài thành artifact trong 30 ngày.

## Tạo bộ cài trực tiếp trên Windows

Trên Windows 10/11 64-bit, cài Python 3.11 và Inno Setup 6. Đặt `ffmpeg.exe` và `ffprobe.exe` bản Windows trong thư mục `tools`, rồi chạy `BUILD_EXE_WINDOWS.bat`. Nếu quá trình kết thúc thành công, bộ cài nằm tại `installer_output\KHIETTRAN_Autobeat_Cut_Setup.exe`.

## Lưu ý

- Cần chạy và kiểm tra bộ cài trên máy Windows thực tế trước khi phát hành cho khách hàng.
- Tính năng tự cân chỉnh ánh sáng/màu/cân bằng trắng hiện dùng phân tích ảnh cục bộ theo heuristic, không phải mô hình AI đã huấn luyện hoặc dịch vụ AI đám mây.
- Xem giấy phép FFmpeg và các thư viện phụ thuộc trước khi phân phối phần mềm thương mại.
