import asyncio
import os
from typing import List, Optional
from telegram import Bot
from telegram.constants import ParseMode
from core.database import db
from core.loggers import get_logger
from core.models import EventItem
from processing.exporter import Exporter
from config.settings import settings

logger = get_logger("bot.notifier")


class BotNotifier:
    def __init__(self, bot: Optional[Bot] = None):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.admin_id = os.getenv("TELEGRAM_ADMIN_ID")
        self.bot = bot or (Bot(token=self.token) if self.token else None)

    async def broadcast_event(self, event: EventItem) -> int:
        """Gửi sự kiện đến các subscriber có đăng ký địa bàn tương ứng."""
        if not self.bot:
            logger.warning("Bot chưa được khởi tạo, bỏ qua broadcast.")
            return 0

        subscribers = db.get_active_subscribers()
        if not subscribers:
            return 0

        message_text = Exporter.format_telegram_message(event)
        sent_count = 0

        for sub in subscribers:
            # Kiểm tra bộ lọc tỉnh thành của người dùng
            if sub.subscribed_provinces != "ALL" and event.province not in sub.subscribed_provinces:
                continue

            # Kiểm tra mức độ ưu tiên tối thiểu
            if sub.min_priority == "CAO" and event.priority.value != "CAO":
                continue

            try:
                await self.bot.send_message(
                    chat_id=sub.chat_id,
                    text=message_text,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False
                )
                sent_count += 1
                await asyncio.sleep(0.05)  # Tránh Telegram Flood Limit (30 msg/sec)
            except Exception as e:
                logger.error(f"Không thể gửi tin tới {sub.chat_id}: {e}")

        # Đánh dấu đã bắn cảnh báo
        if event.id:
            db.mark_event_alerted(event.id)

        return sent_count

    async def broadcast_urgent_event(self, event: EventItem):
        """Bắn cảnh báo khẩn cấp cho toàn bộ subscriber khi có sự kiện đặc biệt lớn."""
        logger.info(f"Bắn cảnh báo khẩn cấp: {event.canonical_name}")
        await self.broadcast_event(event)

    async def notify_unregistered_source(self, event: EventItem, real_url: str):
        """Gửi cảnh báo phát hiện nguồn tin mới chưa cấu hình tới Admin (HITL)."""
        if not self.bot or not self.admin_id:
            return

        msg = (
            "🚨 *[PHÁT HIỆN NGUỒN TIN MỚI - HITL]*\n\n"
            f"Hệ thống phát hiện sự kiện từ nguồn lạ:\n"
            f"📌 Sự kiện: *{event.canonical_name}*\n"
            f"📍 Tỉnh: *{event.province}*\n"
            f"🔗 Link: {real_url}\n\n"
            f"👉 Bạn có muốn thêm nguồn này vào `sources.yaml` không?"
        )
        try:
            await self.bot.send_message(
                chat_id=int(self.admin_id),
                text=msg,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Lỗi gửi cảnh báo HITL tới admin: {e}")

    async def notify_source_error(self, source_name: str, source_url: str, error_message: str):
        """Tự động gửi thông báo cho Admin khi một nguồn thu thập dữ liệu bị lỗi/hỏng."""
        admin_id = str(settings.TELEGRAM_ADMIN_ID).strip()
        if not admin_id or admin_id == "0":
            return

        error_text = (
            "⚠️ *CẢNH BÁO: NGUỒN CÀO DỮ LIỆU BỊ LỖI*\n\n"
            f"• *Tên nguồn:* `{source_name}`\n"
            f"• *URL:* {source_url}\n"
            f"• *Chi tiết lỗi:* `{error_message[:200]}`\n\n"
            "🛠 _Vui lòng kiểm tra lại cấu trúc web hoặc link RSS của nguồn này trong sources.yaml._"
        )
        try:
            if not self.bot:
                from telegram import Bot
                self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

            from telegram.constants import ParseMode
            await self.bot.send_message(
                chat_id=int(admin_id),
                text=error_text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            logger.warning(f"Đã gửi cảnh báo nguồn hỏng '{source_name}' đến Admin ({admin_id}).")
        except Exception as e:
            logger.error(f"Không thể gửi thông báo lỗi nguồn đến Admin: {e}")


notifier = BotNotifier()