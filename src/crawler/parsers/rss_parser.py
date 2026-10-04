import logging
from typing import List, Dict
import feedparser

logger = logging.getLogger(__name__)


class RSSParser:
    @staticmethod
    def parse(content: bytes, source_meta: dict) -> List[Dict]:
        items = []
        feed = feedparser.parse(content)
        
        if feed.bozo and len(feed.entries) == 0:
            logger.warning(f"Lỗi parse RSS cho nguồn {source_meta.get('name')}: {feed.bozo_exception}")
            return items

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            pub_date = entry.get("published", "") or entry.get("updated", "")

            if title and link:
                items.append({
                    "title": title,
                    "url": link,
                    "raw_text": f"{title}. {summary}",
                    "published_at": pub_date,
                    "source_name": source_meta.get("name"),
                    "province": source_meta.get("province", "ALL"),
                    "source_type": "rss"
                })
        return items