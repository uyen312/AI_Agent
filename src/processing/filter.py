import re
from typing import Dict, List, Optional
from config.settings import settings
from src.core.loggers import get_logger
from src.core.models import RawArticle

logger = get_logger("processing.filter")

# Bổ sung các địa danh/tên gọi đặc trưng cho toàn bộ các tỉnh miền Nam
PROVINCE_EXTRA_ALIASES: Dict[str, List[str]] = {
    # 8 tỉnh ban đầu
    "TP. Hồ Chí Minh": ["hồ chí minh", "tp.hcm", "tphcm", "sài gòn", "quận 1", "thủ đức", "phố đi bộ nguyễn huệ"],
    "Đồng Nai": ["đồng nai", "biên hòa", "long khánh", "chùa ông", "trị an"],
    "Tây Ninh": ["tây ninh", "núi bà đen", "tòa thánh", "trảng bàng"],
    "An Giang": ["an giang", "long xuyên", "châu đốc", "bà chúa xứ", "núi sam", "bảy núi", "đua bò"],
    "Đồng Tháp": ["đồng tháp", "cao lãnh", "sa đéc", "gò tháp", "làng hoa sa đéc", "tràm chim"],
    "Vĩnh Long": ["vĩnh long", "bình minh", "long hồ", "cù lao an bình"],
    "Cần Thơ": ["cần thơ", "ninh kiều", "cái răng", "bến ninh kiều", "chợ nổi cái răng"],
    "Cà Mau": ["cà mau", "năm căn", "u minh", "đất mũi", "đầm dơi"],
    # Các tỉnh miền Nam mở rộng thêm
    "Bình Dương": ["bình dương", "thủ dầu một", "dĩ an", "thuận an", "bến cát", "thành phố mới"],
    "Bà Rịa - Vũng Tàu": ["bà rịa", "vũng tàu", "bãi trước", "bãi sau", "côn đảo", "long hải"],
    "Bình Phước": ["bình phước", "đồng xoài", "phước long", "bình long", "bù đăng"],
    "Long An": ["long an", "tân an", "bến lức", "đức hòa", "cần giuộc"],
    "Tiền Giang": ["tiền giang", "mỹ tho", "gò công", "cái bè", "thới sơn"],
    "Bến Tre": ["bến tre", "mỏ cày", "châu thành", "xứ dừa", "cồn phụng"],
    "Trà Vinh": ["trà vinh", "càng long", "cầu kè", "chùa hang", "ao bà om"],
    "Kiên Giang": ["kiên giang", "rạch giá", "hà tiên", "phú quốc", "nam du"],
    "Hậu Giang": ["hậu gian", "vị thanh", "ngã bảy", "lung ngọc hoàng"],
    "Sóc Trăng": ["sóc trăng", "vĩnh châu", "ngã năm", "chùa dơi", "chùa chén kiểu", "ok om bok"],
    "Bạc Liêu": ["bạc liêu", "giá rai", "nhà công tử bạc liêu", "nhà hát nón lá", "cánh đồng điện gió"],
}


def _build_province_keywords() -> Dict[str, List[str]]:
    """Tự động đồng bộ từ khóa với settings.TARGET_PROVINCES."""
    keywords_map = {}
    for prov in settings.TARGET_PROVINCES:
        base_names = [
            prov.lower(),
            prov.lower().replace("-", " "),
            prov.lower().replace(".", ""),
        ]
        extra = PROVINCE_EXTRA_ALIASES.get(prov, [])
        # Hợp nhất và khử trùng từ khóa
        keywords_map[prov] = list(set(base_names + [x.lower() for x in extra]))
    return keywords_map


PROVINCE_KEYWORDS = _build_province_keywords()

EVENT_KEYWORDS = [
    "lễ hội", "festival", "hội thi", "triển lãm", "liveshow", "concert",
    "đêm nhạc", "bắn pháo hoa", "countdown", "marathon", "giải chạy",
    "hội chợ", "workshop", "kỷ niệm", "khai mạc", "bế mạc", "ẩm thực",
    "tuần lễ du lịch", "đua ghe ngo", "hội xuân", "đại nhạc hội"
]

EXCLUDE_KEYWORDS = [
    "tai nạn", "bắt giữ", "khởi tố", "cháy", "đâm chém", "cướp giật",
    "ma túy", "lừa đảo", "qua đời", "tử vong", "thiệt mạng"
]


class EventFilter:
    @staticmethod
    def detect_province(text: str, default_province: str = "ALL") -> Optional[str]:
        """Xác định tỉnh thành dựa trên nội dung bài viết."""
        text_lower = text.lower()
        if default_province and default_province != "ALL":
            return default_province

        for prov, aliases in PROVINCE_KEYWORDS.items():
            if any(alias in text_lower for alias in aliases):
                return prov
        return None

    @classmethod
    def is_event_candidate(cls, article: RawArticle) -> bool:
        """Kiểm tra bài báo có tiềm năng là sự kiện thuộc địa bàn mục tiêu hay không."""
        if article.source_type == "ticketing":
            return True

        # Sửa lỗi slice NoneType an toàn
        raw_snippet = article.raw_text[:500] if article.raw_text else ""
        text_to_check = f"{article.title} {article.summary or ''} {raw_snippet}".lower()

        # 1. Loại bỏ tin tiêu cực
        if any(neg in text_to_check for neg in EXCLUDE_KEYWORDS):
            return False

        # 2. Kiểm tra từ khóa sự kiện
        has_event_signal = any(kw in text_to_check for kw in EVENT_KEYWORDS)
        if not has_event_signal:
            return False

        # 3. Kiểm tra địa bàn mục tiêu
        matched_province = cls.detect_province(text_to_check, article.province)
        return matched_province is not None

    @classmethod
    def filter_batch(cls, articles: List[RawArticle]) -> List[RawArticle]:
        """Lọc danh sách bài viết thô."""
        candidates = [art for art in articles if cls.is_event_candidate(art)]
        logger.info(f"Bộ lọc sơ bộ: {len(candidates)}/{len(articles)} bài viết hợp lệ.")
        return candidates