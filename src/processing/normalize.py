import re
from datetime import datetime
from src.core.models import EventItem


class Normalizer:
    VALID_PROVINCES = [
        "TP. Hồ Chí Minh", "Đồng Nai", "Tây Ninh", "An Giang",
        "Đồng Tháp", "Vĩnh Long", "Cần Thơ", "Cà Mau"
    ]

    @classmethod
    def normalize_province(cls, text: str) -> str:
        """Đưa tên tỉnh về đúng chuẩn trong danh mục 8 tỉnh miền Nam."""
        if not text:
            return "TP. Hồ Chí Minh"
        t = text.lower()
        if "hồ chí minh" in t or "hcm" in t or "sài gòn" in t:
            return "TP. Hồ Chí Minh"
        if "đồng nai" in t or "biên hòa" in t:
            return "Đồng Nai"
        if "tây ninh" in t:
            return "Tây Ninh"
        if "an giang" in t or "châu đốc" in t:
            return "An Giang"
        if "đồng tháp" in t or "cao lãnh" in t or "sa đéc" in t:
            return "Đồng Tháp"
        if "vĩnh long" in t:
            return "Vĩnh Long"
        if "cần thơ" in t:
            return "Cần Thơ"
        if "cà mau" in t:
            return "Cà Mau"
        return "TP. Hồ Chí Minh"

    @staticmethod
    def normalize_date(date_str: str) -> str:
        """Đảm bảo chuỗi ngày ra định dạng YYYY-MM-DD."""
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        
        # Tìm mẫu dạng YYYY-MM-DD
        match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str)
        if match:
            y, m, d = match.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"

        # Tìm mẫu dạng DD/MM/YYYY
        match_vn = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if match_vn:
            d, m, y = match_vn.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"

        return datetime.now().strftime("%Y-%m-%d")

    @classmethod
    def clean(cls, item: EventItem) -> EventItem:
        """Chuẩn hóa toàn diện một EventItem."""
        item.province = cls.normalize_province(item.province)
        item.start_date = cls.normalize_date(item.start_date)
        item.end_date = cls.normalize_date(item.end_date)
        if item.end_date < item.start_date:
            item.end_date = item.start_date

        item.canonical_name = re.sub(r"\s+", " ", item.canonical_name).strip()
        return item