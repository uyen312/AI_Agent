import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class APIParser:
    @staticmethod
    def parse_ticketbox(json_data: dict, source_meta: dict) -> List[Dict]:
        items = []
        if not isinstance(json_data, dict):
            return items

        # Trích xuất mảng results theo format thực tế
        data_body = json_data.get("data", {})
        results = data_body.get("results", []) if isinstance(data_body, dict) else []

        for ev in results:
            name = ev.get("name") or ev.get("title")
            link = ev.get("deeplink") or ev.get("url") or source_meta.get("url")
            day = ev.get("day") or ev.get("startDate")
            price = ev.get("price", "N/A")

            if name:
                items.append({
                    "title": name,
                    "url": link,
                    "raw_text": f"Sự kiện: {name}. Thời gian: {day}. Giá vé: {price} VND.",
                    "published_at": day,
                    "source_name": source_meta.get("name"),
                    "province": source_meta.get("province", "TP. Hồ Chí Minh"),
                    "source_type": "ticketing",
                    "structured_hint": {
                        "date": day,
                        "price": price
                    }
                })
        return items