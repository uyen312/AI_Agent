import os
from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Đường dẫn thư mục gốc của toàn bộ dự án
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    # ==========================================
    # 1. TIMEZONE & HỆ THỐNG
    # ==========================================
    TIMEZONE: str = Field(default="Asia/Ho_Chi_Minh", description="Múi giờ chuẩn Việt Nam GMT+7")
    LOG_LEVEL: str = Field(default="INFO", description="Mức độ ghi log: DEBUG, INFO, WARNING, ERROR")
    
    # ==========================================
    # 2. ĐƯỜNG DẪN THƯ MỤC & DATABASE
    # ==========================================
    BASE_DIR: Path = ROOT_DIR
    DATA_DIR: Path = ROOT_DIR / "data"
    LOGS_DIR: Path = ROOT_DIR / "data" / "logs"
    DB_PATH: Path = Field(
        default=ROOT_DIR / "data" / "events.db",
        validation_alias="DATABASE_PATH"
    )
    SOURCES_CONFIG_PATH: Path = ROOT_DIR / "config" / "sources.yaml"

    # ==========================================
    # 3. GOOGLE GEMINI AI CONFIG
    # ==========================================
    GEMINI_API_KEY: str = Field(default="", description="API Key từ Google AI Studio")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", description="Mô hình Gemini bóc tách JSON")
    GEMINI_TEMPERATURE: float = Field(default=0.1, description="Độ sáng tạo thấp để bóc JSON chuẩn xác")

    # ==========================================
    # 4. TELEGRAM BOT CONFIG
    # ==========================================
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Token Bot lấy từ BotFather")
    TELEGRAM_ADMIN_ID: int = Field(default=0, description="Chat ID tài khoản Admin quản trị")

    # ==========================================
    # 5. SCHEDULER & CRAWLER SETTINGS
    # ==========================================
    CRAWL_INTERVAL_HOURS: int = Field(default=6, description="Chu kỳ chạy cào tự động (giờ)")
    REQUEST_TIMEOUT: int = Field(default=15, description="Timeout gọi HTTP / RSS (giây)")
    MAX_ARTICLES_PER_SOURCE: int = Field(default=10, description="Số bài tối đa lấy mỗi nguồn mỗi lần cào")

    # ==========================================
    # 6. ĐỊA BÀN 8 TỈNH MIỀN NAM
    # ==========================================
    TARGET_PROVINCES: List[str] = [
        "TP. Hồ Chí Minh",
        "Đồng Nai",
        "Tây Ninh",
        "An Giang",
        "Đồng Tháp",
        "Vĩnh Long",
        "Cần Thơ",
        "Cà Mau",
    ]
    # # Toàn bộ địa bàn các tỉnh miền Nam
    # TARGET_PROVINCES: List[str] = [
    #     # Đông Nam Bộ
    #     "TP. Hồ Chí Minh", "Bình Dương", "Đồng Nai", "Bà Rịa - Vũng Tàu", "Tây Ninh", "Bình Phước",
    #     # Tây Nam Bộ (ĐBSCL)
    #     "Cần Thơ", "Long An", "Tiền Giang", "Bến Tre", "Trà Vinh", "Vĩnh Long", 
    #     "Đồng Tháp", "An Giang", "Kiên Giang", "Hậu Giang", "Sóc Trăng", "Bạc Liêu", "Cà Mau"
    # ]

    # Cấu hình Pydantic đọc trực tiếp từ file .env
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Bỏ qua biến dư thừa trong .env mà không gây crash
    )

    def init_environment(self):
        """Khởi tạo thư mục và gán biến môi trường hệ thống."""
        # 1. Tự động tạo thư mục data/ và logs/ nếu chưa có
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # 2. Thiết lập biến môi trường múi giờ cho toàn bộ tiến trình Python
        os.environ["TZ"] = self.TIMEZONE
        try:
            import time
            time.tzset()  # Chỉ chạy trên Linux/macOS, Windows sẽ bỏ qua không lỗi
        except AttributeError:
            pass


# Khởi tạo instance dùng chung toàn dự án
settings = Settings()
settings.init_environment()