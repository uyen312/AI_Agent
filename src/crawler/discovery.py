import asyncio
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Set
import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup

from config.settings import settings
from core.database import db
from core.loggers import get_logger
from core.models import EventItem, RawArticle
from processing.dedup import Deduplicator
from processing.filter import EventFilter
from processing.llm_extractor import LLMExtractor
from processing.normalize import Normalizer
from bot.notifier import notifier

logger = get_logger("crawler.discovery")

# Từ khóa tìm kiếm trọng tâm bám sát thực tế báo chí địa phương
EVENT_SEARCH_TERMS = [
    "marathon",
    "giải chạy",
    "lễ hội",
    "đại nhạc hội",
    "bắn pháo hoa",
    "tuần lễ văn hóa",
    "ẩm thực du lịch",
    "ngày hội"
]


class AISearchDiscovery:
    def __init__(self):
        self.is_running = False
        self.processed_urls: Set[str] = set()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })

    def _resolve_google_url(self, google_url: str) -> str:
        """
        Giải mã URL Google News sang URL báo gốc thuần túy,
        không phụ thuộc thư viện bên thứ 3 bị lỗi thời.
        """
        try:
            resp = self.session.get(google_url, allow_redirects=True, timeout=8)
            final_url = resp.url
            if "google.com" not in urllib.parse.urlparse(final_url).netloc:
                return final_url

            soup = BeautifulSoup(resp.text, "html.parser")
            # 1. Quét thuộc tính data-n-au trong c-wiz redirect của Google
            cwiz = soup.find("c-wiz", attrs={"data-n-au": True})
            if cwiz and cwiz.get("data-n-au"):
                return cwiz["data-n-au"]

            # 2. Quét thẻ thẻ <a> trong trang redirect
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if href.startswith("http") and "google.com" not in href:
                    return href

            return final_url
        except Exception:
            return google_url

    def _fetch_article_content(self, url: str) -> str:
        """
        Tải và làm sạch toàn văn bài báo bằng trafilatura.
        Giúp Gemini nắm trọn vẹn địa điểm (phường/xã, công viên) và quy mô.
        """
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(
                    downloaded, 
                    include_comments=False, 
                    include_tables=True, 
                    no_fallback=False
                )
                return text or ""
        except Exception as e:
            logger.debug(f"Không thể tải nội dung từ {url}: {e}")
        return ""

    def _is_unregistered_source(self, real_url: str) -> bool:
        """Kiểm tra xem domain bài viết đã có trong sources.yaml chưa."""
        netloc = urllib.parse.urlparse(real_url).netloc.lower()
        if not netloc or not settings.SOURCES_CONFIG_PATH.exists():
            return False

        import yaml
        try:
            with open(settings.SOURCES_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                for src in cfg.get("sources", []):
                    known_netloc = urllib.parse.urlparse(src.get("url", "")).netloc.lower()
                    if known_netloc and known_netloc in netloc:
                        return False
            return True
        except Exception:
            return False

    async def run_discovery_for_all_provinces(self) -> int:
        """
        Tiến trình Autonomous Web Discovery:
        Tự động tìm kiếm các bài viết / sự kiện mới nhất cho toàn bộ 19 tỉnh miền Nam.
        """
        if self.is_running:
            logger.warning("Tiến trình Autonomous Discovery đang chạy, bỏ qua yêu cầu mới.")
            return 0

        self.is_running = True
        logger.info("🛰️ === BẮT ĐẦU AUTONOMOUS AI WEB DISCOVERY KHẮP MIỀN NAM ===")
        total_discovered = 0

        try:
            provinces = settings.TARGET_PROVINCES
            logger.info(f"Đang kích hoạt tìm kiếm sự kiện cho {len(provinces)} tỉnh/thành...")

            for prov_name in provinces:
                logger.info(f"-> Quét bài viết sự kiện cho địa bàn: [{prov_name}]...")
                count = await self._discover_for_province(prov_name)
                total_discovered += count
                # Khoảng nghỉ nhẹ giữa các tỉnh để không làm nghẽn mạng
                await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"Lỗi trong tiến trình Autonomous Discovery: {e}", exc_info=True)
        finally:
            self.is_running = False
            logger.info(f"🛰️ === HOÀN TẤT DISCOVERY: Khám phá thành công {total_discovered} sự kiện mới ===")

        return total_discovered

    async def _discover_for_province(self, province: str) -> int:
        """Dò tìm bài viết mới từ Google News cho 1 tỉnh cụ thể."""
        discovered_count = 0
        extractor = LLMExtractor()

        for term in EVENT_SEARCH_TERMS:
            try:
                # Tìm kiếm bài viết có từ khóa và tên tỉnh trong vòng 7 ngày gần nhất
                query = f'{term} "{province}"'
                rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}+when:7d&hl=vi&gl=VN&ceid=VN:vi"
                
                # feedparser là blocking I/O, chạy qua to_thread
                feed = await asyncio.to_thread(feedparser.parse, rss_url)
                if not feed.entries:
                    continue

                for entry in feed.entries[:3]:
                    title = entry.get("title", "")
                    gnews_link = entry.get("link", "")
                    if not gnews_link:
                        continue

                    # 1. Giải mã link gốc
                    real_url = await asyncio.to_thread(self._resolve_google_url, gnews_link)
                    if real_url in self.processed_urls:
                        continue
                    self.processed_urls.add(real_url)

                    # 2. Tải toàn văn bài báo chi tiết
                    content = await asyncio.to_thread(self._fetch_article_content, real_url)
                    summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()

                    # Nếu không cào được nội dung hoặc bài quá ngắn -> dùng tạm summary
                    full_text = content if (content and len(content) >= 120) else summary

                    # Tách tên nguồn nếu có dạng 'Tiêu đề - Báo Đồng Tháp'
                    source_name = urllib.parse.urlparse(real_url).netloc
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        title, source_name = parts[0], parts[1]

                    raw_article = RawArticle(
                        title=title,
                        url=real_url,
                        summary=summary,
                        raw_text=full_text,
                        province=province,
                        source_name=source_name,
                        source_type="discovery_news",
                        discovered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )

                    # 3. Lọc nhanh sơ bộ (chống tin tiêu cực, kiểm tra từ khóa)
                    if not EventFilter.is_event_candidate(raw_article):
                        continue

                    # 4. Trích xuất cấu trúc sự kiện với Gemini LLM
                    event_item = await asyncio.to_thread(extractor.extract, raw_article)
                    if not event_item:
                        continue

                    # 5. Làm sạch và chuẩn hóa dữ liệu
                    cleaned_event = Normalizer.clean(event_item)

                    # 6. Khử trùng lặp với CSDL SQLite
                    existing_candidates = db.get_upcoming_events(
                        from_date=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
                        to_date=(datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d"),
                        province=cleaned_event.province
                    )
                    
                    # Tìm xem sự kiện đã từng tồn tại chưa
                    is_dup, match_item = Deduplicator.is_duplicate_event(cleaned_event, existing_candidates)
                    if is_dup and match_item:
                        # Hợp nhất nguồn mới vào sự kiện cũ nếu chưa có
                        if cleaned_event.source_urls and cleaned_event.source_urls[0] not in match_item.source_urls:
                            match_item.source_urls.extend(cleaned_event.source_urls)
                            db.upsert_event(match_item)
                            logger.info(f"🔄 Đã hợp nhất thêm nguồn cho sự kiện: {match_item.canonical_name}")
                        continue

                    # 7. Lưu sự kiện mới vào Database
                    is_new = db.upsert_event(cleaned_event)
                    if is_new:
                        discovered_count += 1
                        logger.info(f"🎯 [DISCOVERY] PHÁT HIỆN SỰ KIỆN MỚI: {cleaned_event.canonical_name} ({cleaned_event.province})")

                        # 8. Cơ chế HITL: Báo Admin nếu phát hiện nguồn báo địa phương mới chưa có trong sources.yaml
                        if self._is_unregistered_source(real_url):
                            logger.info(f"Phát hiện nguồn mới chưa đăng ký: {real_url} -> Gửi HITL Alert...")
                            if hasattr(notifier, "notify_unregistered_source"):
                                await notifier.notify_unregistered_source(cleaned_event, real_url)

                        # 9. Cảnh báo khẩn cấp tức thời (Quy mô lớn / Có pháo hoa / Mức CAO)
                        prio_val = getattr(cleaned_event.priority, "value", str(cleaned_event.priority))
                        if prio_val == "CAO" or cleaned_event.scale_estimate >= 10000 or cleaned_event.has_fireworks:
                            logger.info(f"🚨 Phát hiện sự kiện đặc biệt khẩn cấp: {cleaned_event.canonical_name}")
                            await notifier.broadcast_urgent_event(cleaned_event)

                    # Khoảng nghỉ tuân thủ Quota Gemini API (tránh 429 Too Many Requests)
                    await asyncio.sleep(4.0)

            except Exception as e:
                logger.debug(f"Bỏ qua lỗi truy vấn tìm kiếm [{term} - {province}]: {e}")

        return discovered_count


ai_search_discovery = AISearchDiscovery()