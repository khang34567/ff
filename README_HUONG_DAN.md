# Hệ Thống Điều Khiển Cảm Ứng & Quét Tâm Đỏ Qua Wi-Fi (Không Dùng ADB)

Dự án bao gồm đầy đủ mã nguồn và kịch bản tự động biên dịch cho 2 ứng dụng:
1. **`RemoteTouch_Android.apk`** (Dành cho điện thoại Android / Samsung Galaxy A02s)
2. **`PC_Controller.exe`** (Dành cho máy tính Windows)

## Cách Xuất Nhanh 2 File `.apk` và `.exe` (Chỉ 1 Cú Nhấp Chuột)

### Cách 1: Chạy trực tiếp trên máy tính Windows (`AUTO_BUILD.bat`)
1. Giải nén file `RemoteTouch_Full_Project.zip` ra một thư mục trên máy tính Windows (có kết nối Internet).
2. Nhấp đúp chuột vào file **`AUTO_BUILD.bat`**.
3. Kịch bản sẽ tự động tải công cụ cần thiết (PyInstaller, OpenJDK 17, Android SDK, Gradle) và xuất sẵn 2 file chạy hoàn chỉnh vào thư mục **`OUTPUT_FILES/`**:
   - `OUTPUT_FILES/RemoteTouch_Android.apk`
   - `OUTPUT_FILES/PC_Controller.exe`

### Cách 2: Đẩy lên GitHub Actions (Không cần cài đặt bất cứ thứ gì trên máy)
1. Tạo 1 repository trên GitHub và tải toàn bộ các file trong bản giải nén lên.
2. Vào tab **Actions** trên GitHub -> Workflow **Auto Build APK and EXE** sẽ tự động chạy và xuất ra 2 gói tải về:
   - **`RemoteTouch_Android_APK`** (chứa `RemoteTouch_Android.apk`)
   - **`PC_Controller_EXE`** (chứa `PC_Controller.exe`)

## Hướng Dẫn Sử Dụng Chi Tiết

### Bước 1: Trên Máy Tính Windows
1. Mở **`PC_Controller.exe`** (hoặc chạy trực tiếp `python PC_Controller/PC_Controller.py`).
2. Khi hộp thoại Windows Firewall hiện ra, tích chọn **Private networks** và bấm **Allow access** để mở cổng TCP `8888`.
3. Ghi nhớ **Địa chỉ IP LAN của máy tính** hiển thị ở góc trên bên trái cửa sổ (ví dụ: `192.168.1.10`).

### Bước 2: Trên Điện Thoại Android (Samsung Galaxy A02s)
1. Cài đặt và mở ứng dụng **`RemoteTouch_Android.apk`**.
2. Bấm nút **"1. Cấp quyền Trợ năng (Accessibility)"** -> Tìm mục **RemoteTouch Auto Gesture** -> Bật công tắc cho phép.
3. Quay lại ứng dụng, bấm nút **"2. Cấp quyền Chụp màn hình"** -> Chọn **Bắt đầu ngay (Start now)**.
4. Nhập địa chỉ IP LAN của máy tính vào ô nhập liệu và bấm **"3. Kết nối tới PC (Port 8888)"**.

### Bước 3: Tinh Chỉnh Tự Động Vuốt Tâm Đỏ Trên PC
- Màn hình điện thoại sẽ hiển thị trực tiếp theo thời gian thực trên cửa sổ PC kèm ô vuông **30x30 pixel** ngay chính giữa tâm.
- Bấm nút **"CHẾ ĐỘ TỰ ĐỘNG VUỐT"** (hoặc phím tắt **F6**) để bật/tắt.
- Dùng các thanh trượt (Slider) bên phải để điều chỉnh:
  - **Độ dài lực vuốt (Swipe Distance)**: Độ cao đường kéo tâm lên trên.
  - **Tọa độ X / Y vùng vuốt**: Vị trí đặt ngón tay bắt đầu kéo trên màn hình.
  - **Thời gian vuốt (Duration ms)**: Tốc độ vuốt nhanh hay chậm.
  - **Ngưỡng nhạy màu đỏ (%)**: Tỷ lệ pixel đỏ trong ô 30x30 để kích hoạt lệnh `"SWIPE,x1,y1,x2,y2,duration\n"`.
