import asyncio
import sys
import time
from pathlib import Path

# Đảm bảo nhận diện thư mục root
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

import yaml
from config.settings import settings
from core.database import db
from core.loggers import get_logger
from core.models import CrawlLogItem, RawArticle
from crawler.engine import CrawlerEngine
from processing.filter import EventFilter
from processing.llm_extractor import LLMExtractor
from processing.normalize import Normalizer
from processing.dedup import Deduplicator
from processing.exporter import Exporter
from bot.notifier import notifier

logger = get_logger("scripts.trigger_pipeline")


async def run_pipeline():
    start_time = time.time()
    logger.info("🚀 BẮT ĐẦU CHẠY PIPELINE QUA CẤU HÌNH TẬP TRUNG (SETTINGS)...")

    # 1. Đọc danh sách nguồn qua settings.SOURCES_CONFIG_PATH
    if not settings.SOURCES_CONFIG_PATH.exists():
        logger.error(f"Không tìm thấy file nguồn tại: {settings.SOURCES_CONFIG_PATH}")
        return

    with open(settings.SOURCES_CONFIG_PATH, "r", encoding="utf-8") as f:
        sources_cfg = yaml.safe_load(f) or {}
        sources = sources_cfg.get("sources", [])

    logger.info(f"Đã nạp {len(sources)} nguồn cào từ sources.yaml")

    # 2. Thu thập dữ liệu thô
    engine = CrawlerEngine()
    raw_dicts = engine.crawl_all(sources)
    logger.info(f"Thu thập được tổng cộng {len(raw_dicts)} tin bài thô.")

    if not raw_dicts:
        logger.warning("Không có dữ liệu mới để xử lý.")
        return

    # Ép kiểu dữ liệu sang Pydantic RawArticle
    raw_articles = []
    for item in raw_dicts:
        try:
            raw_articles.append(RawArticle(**item))
        except Exception as e:
            logger.debug(f"Bỏ qua item lỗi schema: {e}")

    # 3. Lọc từ khóa sự kiện miền Nam
    candidates = EventFilter.filter_batch(raw_articles)
    logger.info(f"Vượt qua bộ lọc từ khóa địa bàn: {len(candidates)}/{len(raw_articles)} bài.")

    # 4. Trích xuất cấu trúc sự kiện qua Gemini AI
    extractor = LLMExtractor()
    extracted_events = []
    for art in candidates:
        event = extractor.extract(art)
        if event:
            cleaned_event = Normalizer.clean(event)
            extracted_events.append(cleaned_event)
            logger.info(f"  + [AI Extracted] {cleaned_event.canonical_name} ({cleaned_event.province})")

    logger.info(f"AI bóc tách thành công: {len(extracted_events)} sự kiện.")

    # 5. Khử trùng lặp đa nguồn & gộp URLs
    deduped_events = Deduplicator.deduplicate(extracted_events)

    # 6. Lưu vào Database SQLite
    new_saved_count = 0
    for ev in deduped_events:
        is_new = db.upsert_event(ev)
        if is_new:
            new_saved_count += 1
            # 7. Bắn thông báo ngay cho Bot nếu là sự kiện mới
            logger.info(f"📢 Đang gửi thông báo sự kiện mới qua Telegram: {ev.canonical_name}")
            await notifier.broadcast_event(ev)

    execution_time = round(time.time() - start_time, 2)
    logger.info(f"✅ PIPELINE HOÀN TẤT TRONG {execution_time}s! Đã lưu mới: {new_saved_count} sự kiện.")

    # Ghi log lịch sử cào
    db.record_crawl_log(
        CrawlLogItem(
            status="SUCCESS",
            articles_found=len(raw_articles),
            events_extracted=len(deduped_events),
            execution_time_seconds=execution_time,
        )
    )


if __name__ == "__main__":
    asyncio.run(run_pipeline())