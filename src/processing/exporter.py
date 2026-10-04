import json
from pathlib import Path
from typing import List
from src.core.database import db
from src.core.loggers import get_logger
from src.core.models import EventItem
import pandas as pd
from datetime import datetime

logger = get_logger("processing.exporter")


class Exporter:
    @staticmethod
    def _format_date_range(start_date: str, end_date: str) -> str:
        """Chuyển YYYY-MM-DD sang định dạng ngày gọn gàng (VD: 17–18/10 hoặc 15/10)."""
        try:
            d_start = datetime.strptime(start_date, "%Y-%m-%d")
            if not end_date or end_date == start_date:
                return f"{d_start.day}/{d_start.month}"
            
            d_end = datetime.strptime(end_date, "%Y-%m-%d")
            if d_start.month == d_end.month:
                return f"{d_start.day}–{d_end.day}/{d_start.month}"
            return f"{d_start.day}/{d_start.month}–{d_end.day}/{d_end.month}"
        except Exception:
            return start_date

    @staticmethod
    def _get_priority_tag(priority) -> str:
        """Quy đổi mức độ ưu tiên sang thẻ chuẩn: [CAO], [TB], [THẤP]."""
        prio_str = getattr(priority, "value", str(priority)).upper()
        if "CAO" in prio_str or "HIGH" in prio_str:
            return "[CAO]"
        elif "TRUNG" in prio_str or "TB" in prio_str or "MEDIUM" in prio_str:
            return "[TB]"
        return "[THẤP]"

    @classmethod
    def format_daily_bulletin(cls, events: List[EventItem], now: datetime = None) -> str:
        """Định dạng bản tin sáng 07:00 chuẩn 100% theo mẫu của đề bài."""
        if now is None:
            now = datetime.now()

        # Thứ trong tuần bằng tiếng Việt
        weekdays = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        weekday_vn = weekdays[now.weekday()]
        
        # Đếm số sự kiện lớn (>= 10.000 người hoặc có pháo hoa hoặc [CAO])
        large_scale_count = sum(
            1 for ev in events 
            if ev.scale_estimate >= 10000 
            or ev.has_fireworks 
            or cls._get_priority_tag(ev.priority) == "[CAO]"
        )

        # Header bản tin
        lines = [
            f"BẢN TIN SỰ KIỆN MIỀN NAM – 07:00 {weekday_vn} {now.strftime('%d/%m/%Y')}",
            f"7 ngày tới: {len(events)} sự kiện ({large_scale_count} quy mô lớn)",
            ""
        ]

        # Danh sách sự kiện
        for ev in events:
            prio_tag = cls._get_priority_tag(ev.priority)
            date_display = cls._format_date_range(ev.start_date, ev.end_date)
            
            # Dòng 1: [CAO] 17–18/10 · Cần Thơ
            lines.append(f"{prio_tag} {date_display} · {ev.province}")
            # Dòng 2: Tên sự kiện
            lines.append(ev.canonical_name)
            
            # Dòng 3: Địa điểm chi tiết
            loc = ev.location_detail or ev.district_ward or ev.province
            lines.append(f"Địa điểm: {loc}")
            
            # Dòng 4: Quy mô & pháo hoa (nếu có thông tin)
            scale_parts = []
            if ev.scale_estimate > 0:
                scale_parts.append(f"~{ev.scale_estimate:,} người".replace(",", "."))
            if ev.has_fireworks:
                scale_parts.append("có bắn pháo hoa")
            
            if scale_parts:
                lines.append(f"Quy mô: {' · '.join(scale_parts)}")

            # Dòng 5: Link bài gốc
            source_link = ev.source_urls[0] if ev.source_urls else "Đang cập nhật"
            lines.append(f"Nguồn: {source_link}")
            lines.append("")  # Dòng trống ngăn cách các sự kiện

        # Footer điều hướng
        lines.append("Gõ /tuannay để xem đầy đủ, /tinh <tên tỉnh> để lọc.")
        return "\n".join(lines)
    
    @staticmethod
    def save_to_database(events: List[EventItem]) -> int:
        """Lưu toàn bộ sự kiện vào DB, trả về số lượng sự kiện tạo mới."""
        new_count = 0
        for ev in events:
            if db.upsert_event(ev):
                new_count += 1
        logger.info(f"Đã lưu thành công vào SQLite: {new_count} sự kiện mới.")
        return new_count

    @staticmethod
    def export_to_json(events: List[EventItem], output_path: str = "data/events_output.json"):
        """Xuất danh sách sự kiện ra file JSON phục vụ API hoặc kiểm tra."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = [ev.model_dump() for ev in events]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Đã xuất dữ liệu ra file JSON tại {output_path}")

    @staticmethod
    def format_telegram_message(event: EventItem) -> str:
        """Định dạng bản tin sự kiện dạng Markdown đẹp mắt cho Telegram Bot."""
        firework_badge = "🎆 *[CÓ BẮN PHÁO HOA]*\n" if event.has_fireworks else ""
        priority_badge = "🚨 *[ƯU TIÊN CAO]*\n" if event.priority.value == "CAO" else ""

        links = "\n".join([f"  • [Chi tiết bài viết]({u})" for u in event.source_urls[:3]])

        msg = (
            f"{priority_badge}{firework_badge}"
            f"📌 *{event.canonical_name}*\n"
            f"📍 *Địa điểm:* {event.location_detail or event.province} ({event.province})\n"
            f"🗓 *Thời gian:* {event.start_date} -> {event.end_date}\n"
            f"💰 *Vé tham dự:* {event.price}\n"
            f"📝 *Nội dung:* {event.summary or 'Đang cập nhật'}\n"
            f"🔗 *Nguồn tin:*\n{links}"
        )
        return msg

    @staticmethod
    def export_to_excel(events: List[EventItem], output_path: str | Path) -> str:
        """Xuất danh sách sự kiện ra file Excel theo tuần/tháng."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = []
        for idx, ev in enumerate(events, 1):
            data.append({
                "STT": idx,
                "Tên sự kiện": ev.canonical_name,
                "Tỉnh/Thành": ev.province,
                "Quận/Huyện": ev.district_ward or "",
                "Địa điểm chi tiết": ev.location_detail or "",
                "Ngày bắt đầu": ev.start_date,
                "Ngày kết thúc": ev.end_date,
                "Quy mô dự kiến (người)": ev.scale_estimate,
                "Bắn pháo hoa": "Có" if ev.has_fireworks else "Không",
                "Mức độ ưu tiên mạng lưới": ev.priority.value if hasattr(ev.priority, "value") else str(ev.priority),
                "Giá vé": ev.price,
                "Nguồn tin": " | ".join(ev.source_urls) if ev.source_urls else "",
                "Tóm tắt": ev.summary or ""
            })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine="openpyxl")
        return str(output_path)