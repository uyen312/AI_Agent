import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.core.loggers import get_logger
from src.core.models import EventItem, PriorityEnum, RawArticle
from config.settings import settings

# Tự động tìm và nạp file .env từ thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv()  # Fallback nếu chạy ở thư mục hiện hành

logger = get_logger("processing.llm_extractor")


class LLMExtractor:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            logger.warning("Chưa thiết lập GEMINI_API_KEY, chế độ LLM sẽ chạy bằng Fallback Heuristic.")
            self.client = None
        else:
            # Khởi tạo client theo SDK mới google-genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info("Đã kết nối thành công với Google Gemini Client.")

    def extract(self, article: RawArticle) -> Optional[EventItem]:
        """Trích xuất sự kiện từ một bài viết bằng Gemini LLM."""
        if not self.client:
            return self._heuristic_fallback(article)

        provinces_str = ", ".join(settings.TARGET_PROVINCES)

        prompt = f"""
        Bạn là chuyên gia phân loại sự kiện tại miền Nam Việt Nam. Hãy đọc bài viết sau và trích xuất thông tin sự kiện nếu bài viết đề cập đến một sự kiện/lễ hội có thật sắp hoặc đang diễn ra trong năm 2026.

        Tiêu đề: {article.title}
        Nội dung: {article.raw_text[:1800] if article.raw_text else article.summary}
        Tỉnh dự kiến: {article.province}

        Yêu cầu trả về định dạng JSON Schema:
        {{
            "is_event": true/false,
            "canonical_name": "Tên chuẩn hóa ngắn gọn của sự kiện",
            "province": "Bắt buộc chọn 1 trong các tỉnh sau: {provinces_str}",
            "district_ward": "Quận/Huyện nếu có hoặc null",
            "location_detail": "Địa điểm cụ thể hoặc null",
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "price": "Giá vé hoặc Miễn phí",
            "scale_estimate": 0,
            "has_fireworks": false,
            "priority": "CAO" | "TRUNG_BINH" | "THAP",
            "summary": "Tóm tắt 1-2 câu về nội dung chính",
            "evidence_quote": "Đoạn trích dẫn nguyên văn trong bài nói về thời gian/địa điểm"
        }}
        Nếu bài viết không phải sự kiện hoặc diễn ra ngoài 8 tỉnh trên, trả về: {{"is_event": false}}
        """

        try:
            # Sửa tên model hợp lệ: gemini-2.5-flash hoặc gemini-1.5-flash
            response = self.client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text)
            if not data.get("is_event"):
                return None

            priority_str = data.get("priority", "TRUNG_BINH").upper()
            priority_val = getattr(PriorityEnum, priority_str, PriorityEnum.TRUNG_BINH)

            return EventItem(
                canonical_name=data.get("canonical_name", article.title)[:150],
                raw_title=article.title,
                province=data.get("province", article.province),
                district_ward=data.get("district_ward"),
                location_detail=data.get("location_detail"),
                start_date=data.get("start_date") or datetime.now().strftime("%Y-%m-%d"),
                end_date=data.get("end_date") or data.get("start_date") or datetime.now().strftime("%Y-%m-%d"),
                price=data.get("price", "Miễn phí"),
                scale_estimate=int(data.get("scale_estimate") or 0),
                has_fireworks=bool(data.get("has_fireworks", False)),
                priority=priority_val,
                summary=data.get("summary") or article.title,
                evidence_quote=data.get("evidence_quote"),
                source_urls=[article.url],
            )
        except Exception as e:
            logger.error(f"Lỗi gọi Gemini cho '{article.title}': {e}")
            return self._heuristic_fallback(article)

    def _heuristic_fallback(self, article: RawArticle) -> Optional[EventItem]:
        """Cơ chế trích xuất dự phòng khi không có API Key."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        return EventItem(
            canonical_name=article.title[:100],
            raw_title=article.title,
            province=article.province if article.province != "ALL" else "TP. Hồ Chí Minh",
            start_date=today_str,
            end_date=today_str,
            price="Xem link" if article.source_type == "ticketing" else "Miễn phí",
            priority=PriorityEnum.TRUNG_BINH,
            summary=article.summary or article.title,
            source_urls=[article.url],
        )