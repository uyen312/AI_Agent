from difflib import SequenceMatcher
from typing import List
from src.core.loggers import get_logger
from src.core.models import EventItem

logger = get_logger("processing.dedup")


class Deduplicator:
    @staticmethod
    def _is_similar_title(t1: str, t2: str, threshold: float = 0.65) -> bool:
        """Tính độ tương đồng tiêu đề bằng Levenshtein/SequenceMatcher."""
        return SequenceMatcher(None, t1.lower(), t2.lower()).ratio() >= threshold

    @classmethod
    def deduplicate(cls, events: List[EventItem]) -> List[EventItem]:
        """Khử trùng danh sách sự kiện và gộp các link nguồn lại với nhau."""
        if not events:
            return []

        unique_events: List[EventItem] = []

        for current in events:
            merged = False
            for existing in unique_events:
                # Trùng lặp khi: Cùng tỉnh, cùng ngày bắt đầu, và tiêu đề tương tự nhau >= 65%
                same_province = existing.province == current.province
                same_date = existing.start_date == current.start_date
                similar_name = cls._is_similar_title(existing.canonical_name, current.canonical_name)

                if same_province and same_date and similar_name:
                    # Gộp source_urls
                    for u in current.source_urls:
                        if u not in existing.source_urls:
                            existing.source_urls.append(u)
                    
                    # Nâng độ ưu tiên nếu một trong các nguồn báo động mức CAO
                    if current.priority.value == "CAO":
                        existing.priority = current.priority
                    if current.has_fireworks:
                        existing.has_fireworks = True

                    merged = True
                    break

            if not merged:
                unique_events.append(current)

        logger.info(f"Deduplication: Từ {len(events)} sự kiện gộp còn {len(unique_events)} sự kiện duy nhất.")
        return unique_events