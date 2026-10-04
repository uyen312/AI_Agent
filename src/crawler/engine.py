import asyncio
import logging
from typing import Dict, List, Optional
from crawler.fetcher import Fetcher
from crawler.parsers.rss_parser import RSSParser
from crawler.parsers.api_parser import APIParser
from crawler.parsers.html_parser import HTMLParser
from crawler.html_cleaner import HTMLCleaner
from bot.notifier import notifier

logger = logging.getLogger("crawler.engine")


class CrawlerEngine:
    def __init__(self):
        self.fetcher = Fetcher()

    def _fetch_article_body(self, url: str) -> str:
        """Tải toàn văn bài viết và làm sạch HTML để Gemini có đầy đủ dữ liệu bóc tách."""
        if not url:
            return ""
        try:
            resp = self.fetcher.get(url)
            if resp and resp.status_code == 200:
                return HTMLCleaner.clean_html(resp.text)
        except Exception as e:
            logger.debug(f"Không thể cào bài viết chi tiết từ {url}: {e}")
        return ""

    def _trigger_admin_error_alert(self, source_name: str, source_url: str, error_msg: str):
        """Bắn cảnh báo lỗi nguồn an toàn về Telegram của Admin."""
        try:
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if loop and loop.is_running():
                asyncio.create_task(notifier.notify_source_error(source_name, source_url, error_msg))
            else:
                asyncio.run(notifier.notify_source_error(source_name, source_url, error_msg))
        except Exception as alert_err:
            logger.error(f"Không thể kích hoạt gửi cảnh báo lỗi nguồn đến Admin: {alert_err}")

    def crawl_source(self, source_meta: dict) -> List[Dict]:
        """Thu thập dữ liệu từ 1 nguồn cụ thể (RSS, API Ticketbox, hoặc HTML web)."""
        name = source_meta.get("name", "Unknown")
        url = source_meta.get("url", "")
        s_type = source_meta.get("source_type")
        p_type = source_meta.get("parser_type")

        logger.info(f"Đang thu thập nguồn: {name} ({url})")
        results = []

        try:
            # 1. NGUỒN RSS (Báo địa phương, Cổng thông tin, Báo điện tử)
            if s_type == "rss" or p_type == "rss":
                resp = self.fetcher.get(url)
                if not resp or resp.status_code != 200:
                    raise Exception(f"Không thể kết nối đến URL RSS (HTTP {resp.status_code if resp else 'No response'})")
                
                parsed_items = RSSParser.parse(resp.content, source_meta)
                if not parsed_items:
                    logger.warning(f"RSS rỗng hoặc không phân tích được bài nào: {name}")

                # Lấy chi tiết toàn văn cho 5 bài viết mới nhất từ RSS
                for item in parsed_items[:5]:
                    item_url = item.get("url")
                    full_text = self._fetch_article_body(item_url)
                    # Gán raw_text đầy đủ (nếu tải thất bại thì fallback về summary/title)
                    item["raw_text"] = full_text if full_text else item.get("summary", item.get("title", ""))
                    results.append(item)

            # 2. NGUỒN API BÁN VÉ TICKETBOX
            elif p_type in ["api_json", "dynamic_js_or_internal_api"] or s_type == "ticketing":
                params = {"at": "this-month"} if "ticketbox.vn" in url else {}
                headers = {"Referer": "https://ticketbox.vn/", "Accept": "application/json"}
                resp = self.fetcher.get(url, params=params, headers=headers)
                if not resp or resp.status_code != 200:
                    raise Exception(f"Lỗi gọi Ticketbox API (HTTP {resp.status_code if resp else 'No response'})")
                
                results = APIParser.parse_ticketbox(resp.json(), source_meta)

            # 3. NGUỒN CÀO HTML TRỰC TIẾP TỪ CỔNG THÔNG TIN
            else:
                resp = self.fetcher.get(url)
                if not resp or resp.status_code != 200:
                    raise Exception(f"Lỗi tải HTML danh mục (HTTP {resp.status_code if resp else 'No response'})")

                listing_items = HTMLParser.parse_listing(resp.text, source_meta)
                
                # Tải chi tiết 5 bài viết mới nhất
                for item in listing_items[:5]:
                    item_url = item.get("url")
                    full_text = self._fetch_article_body(item_url)
                    item["raw_text"] = full_text if full_text else item.get("title", "")
                    results.append(item)

            logger.info(f"✅ Thu thập thành công {len(results)} tin từ '{name}'.")

        except Exception as e:
            logger.error(f"❌ Nguồn '{name}' bị lỗi: {e}")
            # Bắn thông báo về Telegram của Admin
            self._trigger_admin_error_alert(name, url, str(e))

        return results

    def crawl_all(self, sources_list: list) -> List[Dict]:
        """Thu thập tuần tự toàn bộ danh sách nguồn đã cấu hình."""
        all_news = []
        for src in sources_list:
            items = self.crawl_source(src)
            all_news.extend(items)
        logger.info(f"Tổng cộng đã cào được {len(all_news)} tin thô từ {len(sources_list)} nguồn.")
        return all_news