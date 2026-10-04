import asyncio
import html
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config.settings import settings
from core.database import db
from core.loggers import get_logger
from core.models import EventItem, SubscriberItem
from processing.exporter import Exporter

logger = get_logger("bot.handlers")
sec_logger = get_logger("security")

USER_LAST_CALL = defaultdict(float)
COOLDOWN_SECONDS = 3


# ==========================================
# DECORATORS BẢO MẬT & RATE LIMIT
# ==========================================
def admin_only(func):
    """Decorator chỉ cho phép TELEGRAM_ADMIN_ID thực thi lệnh."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        admin_id = str(settings.TELEGRAM_ADMIN_ID).strip()
        if not user or str(user.id) != admin_id:
            sec_logger.warning(f"🚨 Truy cập trái phép lệnh Admin từ ID: {user.id if user else 'Unknown'}")
            await update.message.reply_text("⛔ Lệnh này chỉ dành riêng cho Quản trị viên.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def rate_limit(func):
    """Chống spam lệnh làm nghẽn tài nguyên và cạn Quota."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return
        user_id = user.id
        now = time.time()
        # Admin được miễn trừ giới hạn tốc độ
        if str(user_id) != str(settings.TELEGRAM_ADMIN_ID).strip():
            if now - USER_LAST_CALL[user_id] < COOLDOWN_SECONDS:
                await update.message.reply_text("⏳ Thao tác quá nhanh, vui lòng chờ 3 giây.")
                return
            USER_LAST_CALL[user_id] = now
        return await func(update, context, *args, **kwargs)
    return wrapper


def _format_all_events(events):
    """Format TOÀN BỘ danh sách sự kiện trả về Telegram (không giới hạn số lượng)."""
    if not events:
        return []
    messages = []
    for ev in events:  # Đã bỏ cắt slice [:max_items], lấy toàn bộ
        messages.append(Exporter.format_telegram_message(ev))
    return messages


# ==========================================
# HANDLERS NGƯỜI DÙNG (IN HẾT KHÔNG GIỚI HẠN)
# ==========================================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /start: Đăng ký subscriber và hướng dẫn sử dụng."""
    user = update.effective_user
    chat = update.effective_chat

    sub = SubscriberItem(
        chat_id=chat.id,
        chat_type=chat.type,
        full_name=user.full_name or "Unknown",
        subscribed_provinces="ALL",
        min_priority="ALL",
        is_active=True,
    )
    db.register_subscriber(sub)

    welcome_text = (
        f"👋 Xin chào *{user.first_name}*!\n\n"
        "Chào mừng bạn đến với **AI Event Agent** — Kênh theo dõi & cảnh báo sự kiện, lễ hội miền Nam.\n\n"
        "🔍 *DANH SÁCH LỆNH TRA CỨU:*\n"
        "• `/homnay` — Xem các sự kiện diễn ra hôm nay\n"
        "• `/tuannay` — Xem các sự kiện trong 7 ngày tới\n"
        "• `/tinh <tên tỉnh>` — Tra cứu theo tỉnh (VD: `/tinh Cần Thơ`, `/tinh HCM`)\n"
        "• `/sukien <từ khóa>` — Tìm kiếm theo tên/nội dung (VD: `/sukien marathon`)\n"
        "• `/xuat_excel` — Tải báo cáo sự kiện dạng Excel\n\n"
        "⚙️ *QUẢN LÝ THÔNG BÁO:*\n"
        "• `/sub` — Bật thông báo tự động khi có tin mới\n"
        "• `/unsub` — Tạm ngưng nhận thông báo"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)


@rate_limit
async def homnay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /homnay: Sự kiện trong ngày hôm nay (in tất cả)."""
    today = datetime.now().strftime("%Y-%m-%d")
    events = db.get_upcoming_events(from_date=today, to_date=today)
    if not events:
        await update.message.reply_text("📅 Hôm nay không có sự kiện/lễ hội nào diễn ra.")
        return

    await update.message.reply_text(f"🎯 *HÔM NAY CÓ {len(events)} SỰ KIỆN:*\n", parse_mode=ParseMode.MARKDOWN)
    for msg in _format_all_events(events):
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(0.05)


@rate_limit
async def tuannay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /tuannay: Hiển thị TOÀN BỘ sự kiện trong vòng 7 ngày tới."""
    today = datetime.now()
    next_week = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    events = db.get_upcoming_events(from_date=today_str, to_date=next_week)
    if not events:
        await update.message.reply_text("📅 Trong 7 ngày tới chưa có sự kiện mới nào.")
        return

    await update.message.reply_text(f"🎪 *CÁC SỰ KIỆN TRONG TUẦN NÀY ({len(events)} sự kiện):*", parse_mode=ParseMode.MARKDOWN)
    
    # In toàn bộ sự kiện tìm thấy
    for msg in _format_all_events(events):
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(0.05)


@rate_limit
async def tinh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /tinh <tên tỉnh>: In toàn bộ sự kiện theo tỉnh thành cụ thể."""
    if not context.args:
        prov_list = ", ".join([f"`{p}`" for p in settings.TARGET_PROVINCES[:8]])
        await update.message.reply_text(
            f"⚠️️ Vui lòng nhập tên tỉnh cần tra cứu!\n*Cú pháp:* `/tinh <tên tỉnh>`\n*Ví dụ:* `/tinh Cần Thơ` hoặc `/tinh HCM`\n\nVí dụ các tỉnh:\n{prov_list}...",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    raw_input = " ".join(context.args).strip().lower()
    matched_province = None
    for prov in settings.TARGET_PROVINCES:
        p_lower = prov.lower()
        if raw_input in p_lower or ("hcm" in raw_input and "hồ chí minh" in p_lower) or ("sg" in raw_input and "hồ chí minh" in p_lower):
            matched_province = prov
            break

    search_target = matched_province or " ".join(context.args).strip()
    today = datetime.now().strftime("%Y-%m-%d")
    next_month = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")

    events = db.get_upcoming_events(from_date=today, to_date=next_month, province=search_target)
    if not events:
        await update.message.reply_text(f"📍 Không tìm thấy sự kiện sắp tới tại *{search_target}*.", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text(f"📍 *SỰ KIỆN TẠI {search_target.upper()} ({len(events)} sự kiện):*", parse_mode=ParseMode.MARKDOWN)
    for msg in _format_all_events(events):
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(0.05)


@rate_limit
async def sukien_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /sukien <từ khóa>: In toàn bộ kết quả tìm kiếm (đã bỏ LIMIT 5)."""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Vui lòng nhập từ khóa tìm kiếm!\n*Cú pháp:* `/sukien <từ khóa>`\n*Ví dụ:* `/sukien marathon`, `/sukien ẩm thực`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Làm sạch chuỗi đầu vào
    raw_keyword = " ".join(context.args).strip()[:50]
    keyword = re.sub(r"[\"\'\\;%_]", " ", raw_keyword).strip()
    if not keyword:
        await update.message.reply_text("⚠️ Từ khóa không hợp lệ.")
        return

    # Bỏ LIMIT 5 để lấy toàn bộ dữ liệu khớp
    query = """
        SELECT * FROM events
        WHERE canonical_name LIKE ? OR raw_title LIKE ? OR summary LIKE ? OR location_detail LIKE ?
        ORDER BY start_date DESC
    """
    param = f"%{keyword}%"
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (param, param, param, param))
        rows = [dict(r) for r in cursor.fetchall()]

    if not rows:
        await update.message.reply_text(f"🔍 Không tìm thấy sự kiện nào khớp với: *{keyword}*.", parse_mode=ParseMode.MARKDOWN)
        return

    events = [EventItem(**r) for r in rows]
    await update.message.reply_text(f"🔎 *KẾT QUẢ TÌM KIẾM CHO '{keyword}' ({len(events)} kết quả):*", parse_mode=ParseMode.MARKDOWN)
    for msg in _format_all_events(events):
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(0.05)


async def sub_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db.get_connection() as conn:
        conn.execute("UPDATE subscribers SET is_active = 1 WHERE chat_id = ?", (update.effective_chat.id,))
    await update.message.reply_text("🔔 Đã bật nhận thông báo tự động khi có sự kiện mới!")


async def unsub_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db.get_connection() as conn:
        conn.execute("UPDATE subscribers SET is_active = 0 WHERE chat_id = ?", (update.effective_chat.id,))
    await update.message.reply_text("🔕 Đã tắt thông báo tự động. Dùng `/sub` để bật lại.")


@rate_limit
async def export_excel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /xuat_excel [tuan/thang]: Xuất file Excel sự kiện gửi qua Telegram."""
    arg = context.args[0].lower() if context.args else "tuan"
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    if arg in ["thang", "month"]:
        end_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        period_label = "tháng"
    else:
        end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        period_label = "tuần"

    await update.message.reply_text(f"⏳ Đang kết xuất báo cáo sự kiện theo {period_label}...")
    events = db.get_upcoming_events(from_date=today_str, to_date=end_date)
    if not events:
        await update.message.reply_text(f"Không có sự kiện nào trong {period_label} tới để xuất báo cáo.")
        return

    excel_file = settings.DATA_DIR / f"Bao_cao_su_kien_{arg}_{today.strftime('%Y%m%d')}.xlsx"
    Exporter.export_to_excel(events, excel_file)

    with open(excel_file, "rb") as doc:
        await update.message.reply_document(
            document=doc,
            filename=excel_file.name,
            caption=f"📊 Báo cáo sự kiện {period_label} ({today_str} -> {end_date})\nTổng số: {len(events)} sự kiện.",
            parse_mode=ParseMode.MARKDOWN
        )


# ==========================================
# HANDLERS DÀNH RIÊNG CHO ADMIN
# ==========================================
@admin_only
async def crawl_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /crawl_now: Kích hoạt pipeline ngay lập tức."""
    await update.message.reply_text("⚡ Đang kích hoạt pipeline cào và bóc tách AI tức thì...")
    try:
        from scripts.trigger_pipeline import run_pipeline
        import asyncio
        asyncio.create_task(run_pipeline())
        await update.message.reply_text("🚀 Pipeline đang chạy ngầm, bạn sẽ nhận được thông báo khi hoàn tất!")
    except Exception as e:
        logger.error(f"Lỗi crawl_now: {e}")
        await update.message.reply_text(f"❌ Xảy ra lỗi: {e}")


@admin_only
async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /admin_stats: Xem thống kê hệ thống."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM subscribers WHERE is_active = 1")
        active_subs = cursor.fetchone()[0]

    await update.message.reply_text(
        f"📊 *THỐNG KÊ HỆ THỐNG AGENT*\n\n"
        f"• Tổng số sự kiện: *{total_events}*\n"
        f"• Người đăng ký (active): *{active_subs}*\n"
        f"• Múi giờ: `{settings.TIMEZONE}`\n"
        f"• AI Model: `{settings.GEMINI_MODEL}`",
        parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def admin_backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /admin_backup: Sao lưu database gửi về máy."""
    if not settings.DB_PATH.exists():
        await update.message.reply_text("❌ Không tìm thấy file database.")
        return
    with open(settings.DB_PATH, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=f"backup_events_{int(time.time())}.db",
            caption="🔒 Bản sao lưu Database SQLite an toàn."
        )