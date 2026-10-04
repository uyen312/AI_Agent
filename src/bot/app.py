import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(SRC_DIR))

from flask import app
from telegram.ext import ApplicationBuilder, CommandHandler
from config.settings import settings
from core.loggers import get_logger
from bot.handlers import (
    admin_backup_handler,
    admin_stats_handler,
    start_handler,
    homnay_handler,
    tuannay_handler,
    tinh_handler,
    sukien_handler,
    sub_handler,
    unsub_handler,
    crawl_now_handler,
    export_excel_handler,

)

logger = get_logger("bot.app")


def create_bot_app():
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN chưa được thiết lập!")
        raise ValueError("TELEGRAM_BOT_TOKEN is missing")

    app = ApplicationBuilder().token(token).build()

    # Đăng ký các lệnh theo đúng yêu cầu
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("homnay", homnay_handler))
    app.add_handler(CommandHandler("tuannay", tuannay_handler))
    app.add_handler(CommandHandler("tinh", tinh_handler))
    app.add_handler(CommandHandler("sukien", sukien_handler))
    app.add_handler(CommandHandler("sub", sub_handler))
    app.add_handler(CommandHandler("unsub", unsub_handler))
    app.add_handler(CommandHandler("crawl_now", crawl_now_handler))
    app.add_handler(CommandHandler("xuat_excel", export_excel_handler))
    app.add_handler(CommandHandler("admin_stats", admin_stats_handler))
    app.add_handler(CommandHandler("admin_backup", admin_backup_handler))

    return app


def run_bot():
    logger.info("🤖 Bot đang chạy (Listening for commands)...")
    app = create_bot_app()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()