# 📡 AI Event Agent — Giám Sát Sự Kiện & Lễ Hội Miền Nam (Telecom Planning)

> **Mục tiêu:** Hệ thống tự động thu thập tin tức, ứng dụng AI (Google Gemini) để trích xuất cấu trúc sự kiện tập trung đông người trên địa bàn **19 tỉnh thành miền Nam**. Phục vụ công tác chủ động điều động xe phát sóng lưu động, tăng cường trạm BTS và theo dõi KPI mạng lưới viễn thông.

---

## 🏗️ 1. Kiến Trúc Hoạt Động (6 Khối)

Hệ thống được thiết kế theo luồng khép kín, tự động vận hành 24/7 không phụ thuộc thao tác thủ công:

```
[1. Nguồn tin công khai]
 (UBND, Sở VHTTDL, Báo địa phương, Ticketbox, Google News)
                   │
                   ▼
[2. Thu thập tự động (Crawler Engine & AI Discovery)]
 (Cào RSS, Tải toàn văn bài viết, Quét định kỳ APScheduler)
                   │
                   ▼
[3. Xử lý nội dung (AI Core & Normalization)]
 ├── EventFilter: Loại tin tiêu cực, khớp địa bàn
 ├── Gemini LLM: Trích xuất ngày, giờ, địa điểm chi tiết, quy mô, pháo hoa
 ├── Network Priority: Gán mức độ ưu tiên [CAO], [TB], [THẤP]
 └── Deduplicator: Khử trùng lặp đa nguồn & gộp link bài viết
                   │
                   ▼
[4. CSDL Sự Kiện (SQLite WAL Mode)]
 (Bảng events, Bảng subscribers, Lưu vết trạng thái gửi tin)
                   │
                   ▼
[5. Bot Quản Lý & Nhắn Tin (Telegram Bot API)]
 ├── Phát bản tin sáng lúc 07:00
 ├── Bắn cảnh báo khẩn cấp tức thời (Sự kiện >= 10.000 người, pháo hoa)
 └── Phân quyền Menu Admin vs. Public Menu
                   │
                   ▼
[6. Điện thoại người nhận]
 (Nhận thông báo tự động, tra cứu: /homnay, /tuannay, /tinh, /sukien, /xuat_excel)
```

---

## 📋 2. Yêu Cầu Chuẩn Bị Trước Khi Chạy

1. **Python 3.11+** hoặc máy chủ đã cài đặt **Docker & Docker Compose**.
2. **Telegram Bot Token:** Tạo bot qua [@BotFather](https://t.me/BotFather) để lấy API token.
3. **Telegram Admin ID:** Gõ `/start` với bot [@userinfobot](https://t.me/userinfobot) để lấy chuỗi số Chat ID của bạn.
4. **Google Gemini API Key:** Đăng ký nhận key miễn phí tại [Google AI Studio](https://aistudio.google.com/).

---

## ⚙️ 3. Cấu Hình Biến Môi Trường (`.env`)

Tạo file đặt tên là `.env` ngay tại thư mục gốc của project với cấu hình mẫu sau:

```env
# Token cấp từ BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz

# Chat ID số của bạn để kích hoạt quyền quản trị hệ thống
TELEGRAM_ADMIN_ID=987654321

# Khóa API Google Gemini & Model sử dụng
GEMINI_API_KEY=AIzaSyD-YourGeminiApiKeyHere
GEMINI_MODEL=gemini-2.5-flash

# Đường dẫn lưu trữ Database SQLite
DATABASE_PATH=data/bot_database.db

# Cấu hình múi giờ và chu kỳ cào tin
TIMEZONE=Asia/Ho_Chi_Minh
CRAWL_INTERVAL_HOURS=4
```

---

## 🚀 4. Hướng Dẫn Cài Đặt & Vận Hành

### Phương án 1: Triển khai chuẩn Production với Docker (Khuyên dùng)

Chỉ cần 1 lệnh duy nhất, hệ thống tự động thiết lập môi trường, múi giờ Việt Nam và khởi chạy ngầm 24/7:

```bash
# 1. Khởi chạy và build container chạy ngầm
docker compose up -d --build

# 2. Xem trực tiếp nhật ký hoạt động (logs)
docker compose logs -f

# 3. Dừng hệ thống khi cần
docker compose down
```

---

### Phương án 2: Chạy trực tiếp bằng Python trên máy tính / VPS

#### Bước 1: Khởi tạo môi trường ảo
```bash
# Trên Windows
python -m venv venv
venv\Scripts\activate

# Trên Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

#### Bước 2: Cài đặt các thư viện phụ thuộc
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 3: Khởi chạy Agent
```bash
python main.py
```

Khi terminal xuất hiện các dòng sau là hệ thống đã sẵn sàng:
```text
INFO: [scheduler] Scheduler đã đăng ký đầy đủ các mốc: 06:30 -> 06:45 -> 07:00.
INFO: [system.main] Đã đăng ký Menu lệnh công khai (Default Scope).
INFO: [system.main] Đã đăng ký Menu lệnh bí mật cho Admin Chat ID: ...
INFO: [bot.app] 🤖 Telegram Bot đã kích hoạt Polling và sẵn sàng nhận lệnh!
```

---

## 📱 5. Danh Sách Lệnh Thao Tác Trên Telegram

Mở Telegram, tìm bot của bạn và bấm `/start` để đăng ký nhận bản tin.

### Lệnh Tra Cứu Công Khai (Người dùng thông thường)
| Lệnh | Mô tả |
| :--- | :--- |
| `/homnay` | Xem toàn bộ sự kiện diễn ra trong ngày hôm nay |
| `/tuannay` | Xem danh sách đầy đủ tất cả sự kiện trong 7 ngày tới |
| `/tinh <tên tỉnh>` | Tra cứu theo địa bàn tỉnh (VD: `/tinh Cần Thơ`, `/tinh Đồng Tháp`, `/tinh HCM`) |
| `/sukien <từ khóa>` | Tìm kiếm an toàn theo tên hoặc nội dung (VD: `/sukien marathon`, `/sukien ẩm thực`) |
| `/xuat_excel [tuan/thang]` | Kết xuất và tải danh sách sự kiện ra file bảng tính Excel (`.xlsx`) |
| `/sub` | Bật nhận thông báo tự động khi có sự kiện mới |
| `/unsub` | Tạm dừng nhận thông báo tự động |

### Lệnh Quản Trị Hệ Thống (Chỉ dành riêng cho Admin)
*(Lệnh được ẩn khỏi Menu công khai, bảo vệ bằng Decorator `@admin_only`)*

| Lệnh Admin | Mô tả tính năng |
| :--- | :--- |
| `/crawl_now` | Kích hoạt ngay lập tức tiến trình cào dữ liệu và bóc tách AI mà không cần chờ lịch hẹn |
| `/admin_stats` | Xem thống kê số lượng sự kiện trong database, số lượng subscriber và tình trạng scheduler |
| `/admin_backup` | Bot đóng gói và gửi trực tiếp file SQLite Database về khung chat Admin để sao lưu |

---

## ⏰ 6. Lịch Trình Tự Động Hóa (Automation Timeline)

Hệ thống vận hành đều đặn mỗi ngày theo múi giờ `Asia/Ho_Chi_Minh`:
* **06:30:** Tiến trình **AI Discovery Engine** tự động quét toàn mạng qua Google News cho 19 tỉnh thành miền Nam để tìm kiếm sự kiện mới và cảnh báo domain lạ (HITL - Human in the Loop).
* **06:45:** **Crawler Engine** cào các nguồn tin cố định (cổng thông tin UBND, báo địa phương, Ticketbox) và đưa qua Gemini để phân tích cấu trúc, gắn nhãn `[CAO]`, `[TB]`, `[THẤP]`.
* **07:00:** Tự động gửi **Bản Tin Sáng** tổng hợp các sự kiện 7 ngày tới cho toàn bộ đầu mối đăng ký nhận tin.
* **Thời gian thực:** Bất cứ khi nào phát hiện sự kiện quy mô từ $\ge 10.000$ người hoặc có bắn pháo hoa, hệ thống tự động gửi tin nhắn **Cảnh Báo Khẩn Cấp** tức thời.