import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Thư mục lưu file log mặc định
LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "crawler.log"


class ConsoleColorFormatter(logging.Formatter):
    """Bộ định dạng có màu sắc cho màn hình terminal không cần loguru."""
    
    # Mã màu ANSI
    GREY = "\033[90m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    RESET = "\033[0m"

    FORMAT = "[%(asctime)s] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s"

    FORMATS = {
        logging.DEBUG: GREY + FORMAT + RESET,
        logging.INFO: GREEN + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMAT)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def get_logger(module_name: str = "app") -> logging.Logger:
    """Khởi tạo hoặc lấy logger theo từng module cụ thể."""
    logger = logging.getLogger(module_name)
    
    # Tránh duplicate log khi gọi hàm nhiều lần
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # 1. Console Handler (có màu)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleColorFormatter())
    logger.addHandler(console_handler)

    # 2. File Handler (tự động cắt file khi đạt 10MB, giữ tối đa 5 file backup)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


# Logger mặc định dùng nhanh
logger = get_logger("event_system")