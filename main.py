import asyncio
import os
import signal
import sys
from pathlib import Path
from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import Application

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(SRC_DIR))

from config.settings import settings
from core.database import db
from core.loggers import get_logger
from src.bot.app import create_bot_app
from src.scheduler import production_scheduler

logger = get_logger("system.main")


async def register_bot_commands(app: Application):
    """
    Phân quyền hiển thị Menu:
    - Người dùng thông thường: Chỉ thấy các lệnh tra cứu & xuất file.
    - Admin: Thấy toàn bộ lệnh thường + các lệnh quản trị hệ thống.
    """
    # 1. Danh sách lệnh công khai cho mọi người dùng
    user_commands = [
        BotCommand("homnay", "Xem sự kiện diễn ra trong hôm nay"),
        BotCommand("tuannay", "Xem sự kiện trong 7 ngày tới"),
        BotCommand("tinh", "Tra cứu theo tỉnh (VD: /tinh Cần Thơ)"),
        BotCommand("sukien", "Tìm kiếm theo từ khóa"),
        BotCommand("xuat_excel", "Tải danh sách sự kiện ra file Excel"),
        BotCommand("sub", "Bật nhận thông báo tự động"),
        BotCommand("unsub", "Tắt thông báo tự động"),
    ]

    try:
        # Đăng ký menu mặc định cho tất cả mọi người
        await app.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        logger.info("Đã đăng ký Menu lệnh công khai (Default Scope).")

        # 2. Đăng ký Menu riêng dành cho Admin nếu có TELEGRAM_ADMIN_ID hợp lệ
        admin_id_raw = str(settings.TELEGRAM_ADMIN_ID).strip()
        if admin_id_raw and admin_id_raw.isdigit() and int(admin_id_raw) != 0:
            admin_id = int(admin_id_raw)
            admin_commands = user_commands + [
                BotCommand("admin_stats", "📊 [Admin] Thống kê hệ thống"),
                BotCommand("admin_backup", "🔒 [Admin] Sao lưu database"),
                BotCommand("crawl_now", "⚡ [Admin] Kích hoạt cào tin tức thì"),
            ]
            await app.bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
            logger.info(f"Đã đăng ký Menu lệnh bí mật cho Admin Chat ID: {admin_id}")

    except Exception as e:
        logger.warning(f"Lỗi khi thiết lập Menu lệnh Telegram: {e}")

async def main():
    logger.info("==========================================================")
    logger.info("   🤖 AI EVENT AGENT - SOUTHERN VIETNAM TRACKING BOT     ")
    logger.info("==========================================================")

    # 1. Khởi tạo môi trường & Cơ sở dữ liệu
    settings.init_environment()
    db._init_db()
    logger.info("Cơ sở dữ liệu SQLite (WAL Mode) đã sẵn sàng.")

    # 2. Khởi động Lập lịch (Scheduler)
    production_scheduler.start()

    # 3. Khởi tạo Ứng dụng Telegram Bot
    bot_app = create_bot_app()

    # Quản trị vòng đời Stop an toàn (Graceful Shutdown)
    stop_event = asyncio.Event()

    def handle_exit(*args):
        logger.info("Nhận tín hiệu dừng tiến trình. Đang dọn dẹp tài nguyên...")
        production_scheduler.shutdown()
        stop_event.set()

    # Bắt tín hiệu Ctrl+C tương thích cả Windows và Linux
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_exit)
    else:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)

    # 4. Chạy bot song song với hệ thống
    async with bot_app:
        await bot_app.initialize()
        await register_bot_commands(bot_app)
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("🚀 Hệ thống đang chạy ở chế độ Long Polling. Sẵn sàng nhận lệnh!")

        # Chờ đợi lệnh dừng
        await stop_event.wait()

        # Dừng bot nhẹ nhàng
        await bot_app.updater.stop()
        await bot_app.stop()

    logger.info("🏁 Toàn bộ hệ thống đã tắt an toàn.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass