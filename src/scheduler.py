import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pytz
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(SRC_DIR))

from config.settings import settings
from core.database import db
from core.loggers import get_logger
from core.models import EventItem, RawArticle
from crawler.discovery import ai_search_discovery
from crawler.engine import CrawlerEngine
from processing.dedup import Deduplicator
from processing.filter import EventFilter
from processing.llm_extractor import LLMExtractor
from processing.normalize import Normalizer
from bot.notifier import notifier

logger = get_logger("scheduler")


class ProductionScheduler:
    def __init__(self):
        tz = pytz.timezone(settings.TIMEZONE)
        self.scheduler = AsyncIOScheduler(timezone=tz)
        self.is_crawling = False

    async def job_autonomous_discovery(self):
        """06:30 sáng: Quét chủ động Google News toàn bộ các tỉnh mục tiêu."""
        logger.info("🛰️ [06:30 AM] BẮT ĐẦU CHU TRÌNH AI DISCOVERY KHẮP MIỀN NAM...")
        all_discovered = []

        for province in settings.TARGET_PROVINCES:
            # Chạy trong thread riêng để tránh chặn event loop
            articles = await asyncio.to_thread(
                ai_search_discovery.discover_province, province, max_items_per_term=2
            )
            all_discovered.extend(articles)
            await asyncio.sleep(0.3)

        if not all_discovered:
            logger.info("Discovery không phát hiện thêm tin bài mới.")
            return

        candidates = EventFilter.filter_batch(all_discovered)
        extractor = LLMExtractor()

        for art in candidates:
            ev = extractor.extract(art)
            if ev:
                cleaned_ev = Normalizer.clean(ev)
                is_new = db.upsert_event(cleaned_ev)
                
                # Cảnh báo HITL khi phát hiện domain mới
                if is_new and discovery_engine.check_unregistered_source(art.url):
                    if hasattr(notifier, "notify_unregistered_source"):
                        await notifier.notify_unregistered_source(cleaned_ev, art.url)

        logger.info(f"🛰️ Hoàn tất AI Discovery. Đã xử lý {len(candidates)} bài viết.")

    async def execute_crawl_and_alert_pipeline(self) -> int:
        """Pipeline cào nguồn cố định, phân tích AI và phát cảnh báo sự kiện lớn."""
        if self.is_crawling:
            logger.warning("Một chu trình cào đang chạy, bỏ qua lần này.")
            return 0

        self.is_crawling = True
        logger.info("🔄 [PIPELINE] Bắt đầu cào nguồn cố định...")

        try:
            if not settings.SOURCES_CONFIG_PATH.exists():
                return 0

            with open(settings.SOURCES_CONFIG_PATH, "r", encoding="utf-8") as f:
                sources = (yaml.safe_load(f) or {}).get("sources", [])

            engine = CrawlerEngine()
            raw_dicts = engine.crawl_all(sources)
            if not raw_dicts:
                return 0

            raw_articles = [RawArticle(**d) for d in raw_dicts if "title" in d and "url" in d]
            candidates = EventFilter.filter_batch(raw_articles)

            extractor = LLMExtractor()
            extracted_events = []
            for art in candidates:
                ev = extractor.extract(art)
                if ev:
                    extracted_events.append(Normalizer.clean(ev))
                await asyncio.sleep(0.5)

            deduped_events = Deduplicator.deduplicate(extracted_events)

            new_events_count = 0
            for ev in deduped_events:
                is_new = db.upsert_event(ev)
                if is_new:
                    new_events_count += 1
                    is_urgent = (
                        ev.scale_estimate >= 10000
                        or ev.has_fireworks
                        or (getattr(ev.priority, "value", ev.priority) == "CAO")
                    )
                    if is_urgent:
                        logger.info(f"🚨 Phát hiện sự kiện đặc biệt: {ev.canonical_name}")
                        await notifier.broadcast_urgent_event(ev)

            logger.info(f"✅ Hoàn tất pipeline. Lưu mới {new_events_count} sự kiện.")
            return new_events_count

        except Exception as e:
            logger.error(f"Lỗi pipeline: {e}", exc_info=True)
            return 0
        finally:
            self.is_crawling = False

    async def broadcast_morning_briefing(self):
        """07:00 sáng: Phát bản tin tổng hợp theo đúng mẫu chuẩn."""
        logger.info("☀️ [07:00 AM] Đang phát hành bản tin sáng theo mẫu chuẩn...")
        today = datetime.now()
        next_week = today + timedelta(days=7)

        today_str = today.strftime("%Y-%m-%d")
        next_week_str = next_week.strftime("%Y-%m-%d")

        events = db.get_upcoming_events(from_date=today_str, to_date=next_week_str)
        if not events:
            logger.info("Không có sự kiện nào sắp tới trong 7 ngày.")
            return

        # Định dạng nội dung theo đúng mẫu
        from processing.exporter import Exporter
        message_text = Exporter.format_daily_bulletin(events, now=today)

        # Gửi đến tất cả subscribers
        subscribers = db.get_active_subscribers()
        for sub in subscribers:
            try:
                if notifier.bot:
                    await notifier.bot.send_message(
                        chat_id=sub.chat_id,
                        text=message_text,
                        disable_web_page_preview=True
                    )
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Lỗi gửi bản tin cho {sub.chat_id}: {e}")

    def setup_jobs(self):
        """Đăng ký lịch trình bằng self.<tên_phương_thức>."""
        # 1. 06:30 sáng: Quét Web chủ động
        self.scheduler.add_job(
            self.job_autonomous_discovery,  # Sử dụng self.job_autonomous_discovery
            trigger=CronTrigger(hour=7, minute=0),
            id="job_autonomous_discovery",
            name="Autonomous Web Discovery",
            replace_existing=True,
        )

        # 2. 06:45 sáng: Cào nguồn cố định
        self.scheduler.add_job(
            self.execute_crawl_and_alert_pipeline,
            trigger=CronTrigger(hour=7, minute=15),
            id="job_morning_crawl",
            name="Morning Crawl & AI Extraction",
            replace_existing=True,
        )

        # 3. 07:00 sáng: Phát bản tin sáng
        self.scheduler.add_job(
            self.broadcast_morning_briefing,
            trigger=CronTrigger(hour=7, minute=30),
            id="job_morning_briefing",
            name="Broadcast Daily Morning Bulletin",
            replace_existing=True,
        )

        # 4. Quét cập nhật định kỳ trong ngày
        self.scheduler.add_job(
            self.execute_crawl_and_alert_pipeline,
            trigger=IntervalTrigger(hours=settings.CRAWL_INTERVAL_HOURS),
            id="job_periodic_crawl",
            name="Periodic Crawl",
            replace_existing=True,
        )
        logger.info("Scheduler đã đăng ký đầy đủ các mốc: 06:30 -> 06:45 -> 07:00.")

    def start(self):
        self.setup_jobs()
        self.scheduler.start()

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler đã tắt an toàn.")


production_scheduler = ProductionScheduler()