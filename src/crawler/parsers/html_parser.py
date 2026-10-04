import logging
from typing import List, Dict
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from crawler.html_cleaner import HTMLCleaner

logger = logging.getLogger(__name__)


class HTMLParser:
    @staticmethod
    def parse_listing(html_content: str, source_meta: dict) -> List[Dict]:
        """Bóc tách danh sách tin sơ bộ từ trang chuyên mục tỉnh."""
        items = []
        soup = BeautifulSoup(html_content, "html.parser")
        base_url = source_meta.get("url")
        selectors = source_meta.get("selectors", {})
        container_selector = selectors.get("container") if isinstance(selectors, dict) else None

        articles = soup.select(container_selector) if container_selector else soup.select("article, .news-item, .item-news, .story")

        for art in articles:
            a_tag = art if art.name == "a" else art.find("a", href=True)
            if not a_tag:
                continue

            href = a_tag["href"].strip()
            url = urljoin(base_url, href)
            title = a_tag.get("title") or a_tag.get_text(strip=True)

            if title and url.startswith("http"):
                items.append({
                    "title": title,
                    "url": url,
                    "raw_text": title,
                    "published_at": "",
                    "source_name": source_meta.get("name"),
                    "province": source_meta.get("province", "ALL"),
                    "source_type": "local_news"
                })
        return items