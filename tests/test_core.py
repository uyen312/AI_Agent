import sys
from pathlib import Path

# Thêm cả root và src vào đường dẫn tìm kiếm của Python
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

try:
    from core.database import Database
    from core.loggers import get_logger
    from core.models import EventItem, PriorityEnum, SubscriberItem
except ModuleNotFoundError:
    # Nếu core nằm trong src/
    from src.core.database import Database
    from src.core.loggers import get_logger
    from src.core.models import EventItem, PriorityEnum, SubscriberItem

TEST_DB_PATH = BASE_DIR / "data" / "test_events.db"


def test_logger():
    logger = get_logger("test_module")
    logger.info("Kiểm tra logger hoạt động bình thường.")
    print("[OK] test_logger thành công.")


def test_database_operations():
    # Xóa file test cũ nếu tồn tại
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    db = Database(db_path=TEST_DB_PATH)

    # 1. Test thêm sự kiện mới
    event_1 = EventItem(
        canonical_name="Lễ hội Nghinh Ông Cần Giờ",
        raw_title="Khai mạc Lễ hội Nghinh Ông Cần Giờ 2026",
        province="TP. Hồ Chí Minh",
        start_date="2026-10-15",
        end_date="2026-10-17",
        priority=PriorityEnum.CAO,
        summary="Lễ hội truyền thống ngư dân Cần Giờ",
        source_urls=["https://tuoitre.vn/nghinh-ong-can-gio-1"],
    )
    is_created = db.upsert_event(event_1)
    assert is_created is True, "Sự kiện mới phải tạo thành công!"

    # 2. Test tự động gộp URL khi sự kiện bị trùng tên, ngày, tỉnh
    event_duplicate = EventItem(
        canonical_name="Lễ hội Nghinh Ông Cần Giờ",
        raw_title="Người dân nô nức dự Lễ hội Nghinh Ông",
        province="TP. Hồ Chí Minh",
        start_date="2026-10-15",
        end_date="2026-10-17",
        priority=PriorityEnum.CAO,
        summary="Bài báo thứ hai đưa tin về lễ hội",
        source_urls=["https://vnexpress.net/nghinh-ong-can-gio-2"],
    )
    is_created_dup = db.upsert_event(event_duplicate)
    assert is_created_dup is False, "Sự kiện trùng lặp không được tạo mới mà phải gộp nguồn!"

    # 3. Test truy vấn sự kiện
    events = db.get_upcoming_events(from_date="2026-10-01", to_date="2026-10-31", province="TP. Hồ Chí Minh")
    assert len(events) == 1
    assert len(events[0].source_urls) == 2, "Danh sách source_urls phải có đủ 2 link nguồn gộp!"

    # 4. Test đăng ký subscriber
    sub = SubscriberItem(chat_id=12345678, full_name="Nguyen Van A", subscribed_provinces="TP. Hồ Chí Minh")
    db.register_subscriber(sub)
    active_subs = db.get_active_subscribers()
    assert len(active_subs) == 1
    assert active_subs[0].chat_id == 12345678

    # Dọn dẹp DB test
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    print("[OK] test_database_operations thành công.")


if __name__ == "__main__":
    test_logger()
    test_database_operations()
    print("\n TOÀN BỘ TEST CORE ĐÃ PASS THÀNH CÔNG!")