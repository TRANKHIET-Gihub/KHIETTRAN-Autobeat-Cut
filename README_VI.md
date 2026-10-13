# KHIETTRAN Autobeat Cut — V3.2 source package

Ứng dụng dựng video desktop dựa trên PySide6, OpenCV, librosa và FFmpeg. Bản này nâng cấp trên gói mã nguồn V3.1 hiện có; giữ `main.py` và `autobeat_core.py` để hạn chế rủi ro phá vỡ import.

## Thay đổi trong V3.2

- Đồng bộ tên thương hiệu hiển thị và tên mục tiêu build thành **KHIETTRAN Autobeat Cut**.
- Bổ sung tùy chọn tự động hiệu chỉnh ánh sáng, màu sắc và cân bằng trắng. Mô-đun `autobeat_ai.py` dùng phân tích thị giác máy tính cục bộ, có thể hoạt động offline. Đây là heuristic có giới hạn, không phải mô hình neural AI đã huấn luyện; nên xem trước kết quả trên footage thực tế.
- Bổ sung tùy chọn loại bỏ 2 giây đầu và cuối của từng video nguồn khi thêm clip hoặc dựng tự động. Clip dài không quá 4 giây sẽ bị từ chối trong chế độ cắt này.
- Hoàn thiện bản dịch các thành phần giao diện chính và lựa chọn ngôn ngữ Tiếng Việt/English; mặc định là Tiếng Việt.
- Bổ sung test cho giới hạn hiệu chỉnh màu và logic trim.
- Cập nhật cấu hình PyInstaller và Inno Setup theo tên ứng dụng mới.

## Dependencies

Python 3.11 64-bit khuyến nghị. Cài bằng:

```bat
py -3.11 -m pip install -r requirements.txt
```

FFmpeg và FFprobe phải được cài trong PATH hoặc đặt bản phân phối phù hợp vào `tools\ffmpeg.exe` và `tools\ffprobe.exe`. Chỉ đóng gói FFmpeg có giấy phép phù hợp với cách phân phối của bạn.

## Chạy từ mã nguồn

```bat
py -3.11 -m main
```

## Test

```bat
py -3.11 -m pytest -q
```

Test tự động kiểm tra các helper và cấu hình. Nó không thay thế kiểm thử GUI, render footage thực, chất lượng màu cảm quan hoặc thử nghiệm cài đặt trên máy Windows sạch.

## Build Windows

1. Mở Command Prompt trong thư mục này trên Windows 10/11 64-bit.
2. Cài Python 3.11 64-bit và (nếu cần bộ cài) Inno Setup 6.
3. Chạy `BUILD_EXE_WINDOWS.bat`.
4. EXE dự kiến: `dist\KHIETTRAN Autobeat Cut\KHIETTRAN Autobeat Cut.exe`.
5. Nếu `ISCC.exe` có trong PATH, bộ cài dự kiến: `installer_output\KHIETTRAN_Autobeat_Cut_Setup.exe`.

Không coi build thành công cho đến khi script kết thúc với mã 0 và EXE được chạy thử. Chưa kiểm chứng build Windows trong môi trường Linux này.

## Giới hạn đã biết

- Tự động hiệu chỉnh màu phân tích một khung hình đại diện của mỗi nguồn và dùng điều chỉnh bảo thủ; cảnh có ánh sáng thay đổi mạnh có thể cần chỉnh tay.
- Cắt 2 giây đầu/cuối là cắt theo thời gian, không phải AI phát hiện nội dung. Nếu bật, mỗi nguồn phải dài hơn 4 giây.
- Không có dịch vụ AI đám mây hoặc API key bắt buộc. Không tải footage lên mạng.
- Render 4K/6K/8K và 120 FPS phụ thuộc phần cứng, codec FFmpeg và dung lượng lưu trữ.
