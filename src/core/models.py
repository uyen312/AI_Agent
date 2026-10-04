from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PriorityEnum(str, Enum):
    CAO = "CAO"
    TRUNG_BINH = "TRUNG_BINH"
    THAP = "THAP"


class EventItem(BaseModel):
    id: Optional[int] = None
    canonical_name: str = Field(description="Tên chuẩn hóa của sự kiện, ngắn gọn và rõ ràng")
    raw_title: str = Field(description="Tiêu đề gốc của bài báo")
    province: str = Field(description="Tỉnh/thành phố thuộc 8 tỉnh miền Nam")
    district_ward: Optional[str] = Field(default=None, description="Quận/huyện/xã/phường")
    location_detail: Optional[str] = Field(default=None, description="Địa điểm cụ thể: quảng trường, công viên, chùa...")
    start_date: str = Field(description="Ngày bắt đầu định dạng YYYY-MM-DD")
    end_date: str = Field(description="Ngày kết thúc định dạng YYYY-MM-DD")
    price: Optional[str] = Field(default="Miễn phí", description="Giá vé tham khảo hoặc Miễn phí")
    scale_estimate: int = Field(default=0, description="Ước tính số người tham dự (VD: 10000, 20000)")
    has_fireworks: bool = Field(default=False, description="Có bắn pháo hoa hay không")
    priority: PriorityEnum = Field(default=PriorityEnum.TRUNG_BINH, description="Mức độ ưu tiên mạng lưới: CAO, TRUNG_BINH, THAP")
    summary: Optional[str] = Field(default=None, description="Tóm tắt ngắn gọn nội dung sự kiện")
    evidence_quote: Optional[str] = Field(default=None, description="Trích dẫn chứng minh ngày giờ địa điểm từ bài báo")
    source_urls: List[str] = Field(default_factory=list, description="Danh sách các link nguồn tin tức")
    is_alerted: bool = Field(default=False, description="Đã bắn cảnh báo khẩn cấp chưa")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RawArticle(BaseModel):
    title: str
    url: str  # Dùng url để đồng bộ trực tiếp với module crawler/
    summary: Optional[str] = ""
    raw_text: Optional[str] = ""
    published_date: Optional[str] = None
    source_name: str
    province: Optional[str] = "ALL"
    source_type: Optional[str] = "rss"


class SourceItem(BaseModel):
    id: Optional[int] = None
    name: str
    url: str
    source_type: str = "rss"
    province: str = "ALL"
    is_active: bool = True
    error_count: int = 0
    last_error_message: Optional[str] = None
    last_crawled_at: Optional[datetime] = None


class SubscriberItem(BaseModel):
    chat_id: int
    chat_type: str = "private"
    full_name: Optional[str] = None
    subscribed_provinces: str = "ALL"
    min_priority: str = "ALL"
    is_active: bool = True
    is_verified: bool = False
    created_at: Optional[datetime] = None


class CrawlLogItem(BaseModel):
    id: Optional[int] = None
    source_id: Optional[int] = None
    status: str  # 'SUCCESS', 'FAILED', 'EMPTY'
    articles_found: int = 0
    events_extracted: int = 0
    error_message: Optional[str] = None
    execution_time_seconds: float = 0.0
    created_at: Optional[datetime] = None