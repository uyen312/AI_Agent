import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

from src.core.loggers import get_logger
from src.core.models import CrawlLogItem, EventItem, PriorityEnum, SourceItem, SubscriberItem

logger = get_logger("database")

# Đường dẫn DB mặc định
DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "events.db"


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Tạo kết nối SQLite an toàn với Context Manager và chế độ WAL."""
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        try:
            # Bật Write-Ahead Logging để ghi/đọc đồng thời nhanh và không bị khóa DB
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Lỗi thao tác Database: {e}", exc_info=True)
            raise e
        finally:
            conn.close()

    def _init_db(self):
        """Khởi tạo toàn bộ bảng và index chuẩn hóa."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Bảng lưu sự kiện đã trích xuất & làm sạch
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT NOT NULL,
                    raw_title TEXT NOT NULL,
                    province TEXT NOT NULL,
                    district_ward TEXT,
                    location_detail TEXT,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    price TEXT DEFAULT 'Miễn phí',
                    scale_estimate INTEGER DEFAULT 0,
                    has_fireworks INTEGER DEFAULT 0,
                    priority TEXT DEFAULT 'TRUNG_BINH',
                    summary TEXT,
                    evidence_quote TEXT,
                    source_urls TEXT NOT NULL,  -- Lưu JSON array danh sách link
                    is_alerted INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(canonical_name, start_date, province) -- Chống trùng sự kiện cùng tên, ngày, tỉnh
                );
            """)

            # 2. Bảng theo dõi trạng thái các nguồn cào
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    source_type TEXT DEFAULT 'rss',
                    province TEXT DEFAULT 'ALL',
                    is_active INTEGER DEFAULT 1,
                    error_count INTEGER DEFAULT 0,
                    last_error_message TEXT,
                    last_crawled_at TIMESTAMP
                );
            """)

            # 3. Bảng quản lý người dùng nhận tin Telegram
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id INTEGER PRIMARY KEY,
                    chat_type TEXT DEFAULT 'private',
                    full_name TEXT,
                    subscribed_provinces TEXT DEFAULT 'ALL',
                    min_priority TEXT DEFAULT 'ALL',
                    is_active INTEGER DEFAULT 1,
                    is_verified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 4. Bảng nhật ký crawl
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crawl_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER,
                    status TEXT NOT NULL,
                    articles_found INTEGER DEFAULT 0,
                    events_extracted INTEGER DEFAULT 0,
                    error_message TEXT,
                    execution_time_seconds REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE SET NULL
                );
            """)

            # Tạo Index tăng tốc truy vấn lọc sự kiện cho Bot
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(start_date, end_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_province ON events(province);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_active ON subscribers(is_active);")

    # =========================================================================
    # REPOSITORY METHODS: EVENTS
    # =========================================================================

    def upsert_event(self, event: EventItem) -> bool:
        """Thêm mới sự kiện hoặc gộp URL nguồn nếu đã tồn tại sự kiện tương đương."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Kiểm tra xem sự kiện cùng tên, ngày, tỉnh đã có chưa
            cursor.execute("""
                SELECT id, source_urls FROM events 
                WHERE canonical_name = ? AND start_date = ? AND province = ?
            """, (event.canonical_name, event.start_date, event.province))
            row = cursor.fetchone()

            if row:
                # Sự kiện đã có -> Gộp link nguồn vào danh sách nguồn tin
                event_id = row["id"]
                existing_urls = json.loads(row["source_urls"] or "[]")
                updated_urls = list(set(existing_urls + event.source_urls))

                cursor.execute("""
                    UPDATE events 
                    SET source_urls = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (json.dumps(updated_urls, ensure_ascii=False), event_id))
                return False  # Đã gộp (không phải tạo mới)
            else:
                # Sự kiện mới hoàn toàn
                cursor.execute("""
                    INSERT INTO events (
                        canonical_name, raw_title, province, district_ward, location_detail,
                        start_date, end_date, price, scale_estimate, has_fireworks,
                        priority, summary, evidence_quote, source_urls, is_alerted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.canonical_name,
                    event.raw_title,
                    event.province,
                    event.district_ward,
                    event.location_detail,
                    event.start_date,
                    event.end_date,
                    event.price,
                    event.scale_estimate,
                    1 if event.has_fireworks else 0,
                    event.priority.value,
                    event.summary,
                    event.evidence_quote,
                    json.dumps(event.source_urls, ensure_ascii=False),
                    1 if event.is_alerted else 0,
                ))
                return True

    def get_upcoming_events(self, from_date: str, to_date: str, province: str = "ALL") -> List[EventItem]:
        """Lấy danh sách sự kiện diễn ra trong khoảng thời gian quy định."""
        query = """
            SELECT * FROM events 
            WHERE ((start_date BETWEEN ? AND ?) OR (end_date BETWEEN ? AND ?))
        """
        params = [from_date, to_date, from_date, to_date]

        if province != "ALL":
            query += " AND (province = ? OR province = 'ALL')"
            params.append(province)

        query += " ORDER BY start_date ASC, priority DESC"

        events = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            for row in cursor.fetchall():
                events.append(self._row_to_event_item(row))
        return events

    def get_unalerted_high_priority_events(self) -> List[EventItem]:
        """Lấy danh sách các sự kiện mức độ CAO chưa được gửi cảnh báo."""
        query = """
            SELECT * FROM events 
            WHERE priority = 'CAO' AND is_alerted = 0
            ORDER BY start_date ASC
        """
        events = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            for row in cursor.fetchall():
                events.append(self._row_to_event_item(row))
        return events

    def mark_event_alerted(self, event_id: int):
        """Đánh dấu sự kiện đã phát cảnh báo khẩn cấp."""
        with self.get_connection() as conn:
            conn.execute("UPDATE events SET is_alerted = 1 WHERE id = ?", (event_id,))

    # =========================================================================
    # REPOSITORY METHODS: SUBSCRIBERS
    # =========================================================================

    def register_subscriber(self, sub: SubscriberItem) -> bool:
        """Đăng ký hoặc cập nhật người dùng bot Telegram."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO subscribers (chat_id, chat_type, full_name, subscribed_provinces, min_priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    subscribed_provinces = excluded.subscribed_provinces,
                    min_priority = excluded.min_priority,
                    is_active = 1
            """, (sub.chat_id, sub.chat_type, sub.full_name, sub.subscribed_provinces, sub.min_priority, 1 if sub.is_active else 0))
            return True

    def get_active_subscribers(self) -> List[SubscriberItem]:
        """Lấy danh sách người dùng đang bật thông báo."""
        subs = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscribers WHERE is_active = 1")
            for row in cursor.fetchall():
                subs.append(SubscriberItem(
                    chat_id=row["chat_id"],
                    chat_type=row["chat_type"],
                    full_name=row["full_name"],
                    subscribed_provinces=row["subscribed_provinces"],
                    min_priority=row["min_priority"],
                    is_active=bool(row["is_active"]),
                    is_verified=bool(row["is_verified"]),
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None
                ))
        return subs

    # =========================================================================
    # REPOSITORY METHODS: LOGGING & METRICS
    # =========================================================================

    def record_crawl_log(self, log_item: CrawlLogItem):
        """Ghi nhận nhật ký một lần cào nguồn."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO crawl_logs (source_id, status, articles_found, events_extracted, error_message, execution_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                log_item.source_id,
                log_item.status,
                log_item.articles_found,
                log_item.events_extracted,
                log_item.error_message,
                log_item.execution_time_seconds,
            ))

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _row_to_event_item(row: sqlite3.Row) -> EventItem:
        return EventItem(
            id=row["id"],
            canonical_name=row["canonical_name"],
            raw_title=row["raw_title"],
            province=row["province"],
            district_ward=row["district_ward"],
            location_detail=row["location_detail"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            price=row["price"],
            scale_estimate=row["scale_estimate"],
            has_fireworks=bool(row["has_fireworks"]),
            priority=PriorityEnum(row["priority"]),
            summary=row["summary"],
            evidence_quote=row["evidence_quote"],
            source_urls=json.loads(row["source_urls"] or "[]"),
            is_alerted=bool(row["is_alerted"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )


# Singleton instance
db = Database()