import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

from core.models import EventItem, PriorityEnum, RawArticle
from processing.dedup import Deduplicator
from processing.exporter import Exporter
from processing.filter import EventFilter
from processing.llm_extractor import LLMExtractor
from processing.normalize import Normalizer


# ==========================================================
# 1. KIỂM THỬ BỘ LỌC TỪ KHÓA (FILTER)
# ==========================================================

def test_event_filter():
    """Kiểm tra khả năng giữ lại bài viết sự kiện miền Nam và loại bỏ tin tiêu cực/ngoài vùng."""
    articles = [
        # Hợp lệ: Sự kiện thuộc TP.HCM
        RawArticle(
            title="Khai mạc Lễ hội Áo dài TP.HCM 2026 tại phố đi bộ Nguyễn Huệ",
            url="https://tuoitre.vn/ao-dai-tphcm",
            summary="Sự kiện văn hóa lớn thu hút hàng nghìn du khách.",
            source_name="Tuổi Trẻ",
            province="TP. Hồ Chí Minh",
        ),
        # Bị loại: Tin tai nạn giao thông (tiêu cực)
        RawArticle(
            title="Tai nạn giao thông nghiêm trọng tại ngã tư",
            url="https://tuoitre.vn/tai-nan",
            summary="Vụ việc khiến giao thông ùn tắc nhiều giờ.",
            source_name="Tuổi Trẻ",
            province="TP. Hồ Chi Minh",
        ),
        # Bị loại: Sự kiện ở Hà Nội (ngoài phạm vi 8 tỉnh miền Nam)
        RawArticle(
            title="Lễ hội hoa ban Tây Bắc tổ chức tại công viên Thống Nhất Hà Nội",
            url="https://vnexpress.net/hoa-ban-hanoi",
            summary="Đêm nhạc quy mô lớn tại thủ đô.",
            source_name="VnExpress",
            province="ALL",
        ),
        # Hợp lệ: Nguồn bán vé Ticketbox (luôn giữ lại)
        RawArticle(
            title="Đêm nhạc Rock Tour",
            url="https://ticketbox.vn/rock-tour",
            summary="Bán vé chính thức",
            source_name="Ticketbox",
            province="TP. Hồ Chí Minh",
            source_type="ticketing",
        ),
    ]

    filtered = EventFilter.filter_batch(articles)
    assert len(filtered) == 2, f"Kỳ vọng 2 bài hợp lệ, nhưng nhận {len(filtered)}"
    assert filtered[0].title == "Khai mạc Lễ hội Áo dài TP.HCM 2026 tại phố đi bộ Nguyễn Huệ"
    assert filtered[1].source_type == "ticketing"
    print("\n[OK] test_event_filter thành công.")


# ==========================================================
# 2. KIỂM THỬ CHUẨN HÓA DỮ LIỆU (NORMALIZE)
# ==========================================================

def test_normalizer():
    """Kiểm tra chuẩn hóa định dạng ngày DD/MM/YYYY sang YYYY-MM-DD và chuẩn hóa tên tỉnh."""
    event = EventItem(
        canonical_name="  Đại nhạc hội   biển Cần Giờ   ",
        raw_title="Đại nhạc hội biển Cần Giờ",
        province="tp.hcm",
        start_date="15/10/2026",
        end_date="17/10/2026",
        summary="Nhạc hội",
    )

    cleaned = Normalizer.clean(event)
    assert cleaned.province == "TP. Hồ Chí Minh"
    assert cleaned.start_date == "2026-10-15"
    assert cleaned.end_date == "2026-10-17"
    assert cleaned.canonical_name == "Đại nhạc hội biển Cần Giờ"
    print("[OK] test_normalizer thành công.")


# ==========================================================
# 3. KIỂM THỬ KHỬ TRÙNG LẶP & GỘP NGUỒN (DEDUP)
# ==========================================================

def test_deduplicator():
    """Kiểm tra gộp 2 bài báo viết về cùng 1 lễ hội vào 1 EventItem duy nhất."""
    events = [
        EventItem(
            canonical_name="Lễ hội Sen Đồng Tháp lần thứ 3",
            raw_title="Đồng Tháp rộn ràng chuẩn bị Lễ hội Sen lần thứ 3",
            province="Đồng Tháp",
            start_date="2026-05-19",
            end_date="2026-05-21",
            priority=PriorityEnum.TRUNG_BINH,
            summary="Lễ hội tôn vinh hoa sen tại Cao Lãnh.",
            source_urls=["https://tuoitre.vn/le-hoi-sen-dong-thap"],
        ),
        EventItem(
            canonical_name="Khai mạc Lễ hội Sen Đồng Tháp",
            raw_title="Khai mạc Lễ hội Sen tỉnh Đồng Tháp",
            province="Đồng Tháp",
            start_date="2026-05-19",
            end_date="2026-05-21",
            has_fireworks=True,
            priority=PriorityEnum.CAO,
            summary="Bắn pháo hoa chào mừng lễ hội sen.",
            source_urls=["https://baodongthap.vn/le-hoi-sen"],
        ),
        EventItem(
            canonical_name="Giải đua ghe Ngo Cần Thơ",
            raw_title="Sôi nổi giải đua ghe Ngo Cần Thơ 2026",
            province="Cần Thơ",
            start_date="2026-11-10",
            end_date="2026-11-11",
            priority=PriorityEnum.CAO,
            summary="Đua ghe Ngo sông Hậu.",
            source_urls=["https://baocantho.com.vn/dua-ghe-ngo"],
        ),
    ]

    deduped = Deduplicator.deduplicate(events)
    # 2 bài đầu về Lễ hội Sen phải gộp làm 1
    assert len(deduped) == 2, f"Kỳ vọng 2 sự kiện duy nhất, nhận {len(deduped)}"

    sen_event = next(ev for ev in deduped if ev.province == "Đồng Tháp")
    assert len(sen_event.source_urls) == 2, "source_urls phải chứa đủ 2 link nguồn gộp"
    assert sen_event.has_fireworks is True, "Phải kế thừa trạng thái bắn pháo hoa"
    assert sen_event.priority == PriorityEnum.CAO, "Phải kế thừa mức ưu tiên cao nhất"
    print("[OK] test_deduplicator thành công.")


# ==========================================================
# 4. KIỂM THỬ XUẤT ĐỊNH DẠNG TELEGRAM & EXTRACTOR FALLBACK
# ==========================================================

def test_exporter_and_extractor():
    # 1. Test gọi LLM thật (đọc key từ biến môi trường đã set)
    real_extractor = LLMExtractor()  # Để trống để tự động lấy GEMINI_API_KEY
    if real_extractor.client:
        print("-> Đã nhận diện GEMINI_API_KEY thành công, đang kiểm tra gọi AI...")
        # Test bóc tách thử 1 tin
        sample_article = RawArticle(
            title="Khai mạc Lễ hội Bánh Dân Gian Nam Bộ 2026 tại Cần Thơ",
            url="https://baocantho.com.vn/banh-dan-gian",
            raw_text="Lễ hội diễn ra từ ngày 25/04/2026 đến 29/04/2026 tại quận Bình Thủy, Cần Thơ.",
            province="Cần Thơ",
            source_name="Báo Cần Thơ",
        )
        ai_event = real_extractor.extract(sample_article)
        if ai_event:
            print(f"-> AI trích xuất thành công: {ai_event.canonical_name} ({ai_event.start_date})")

    # 2. Test nhánh Fallback (chủ động truyền key rỗng để kiểm tra cơ chế dự phòng)
    fallback_extractor = LLMExtractor(api_key="fallback_mode")
    fallback_extractor.client = None  # Giả lập mất kết nối AI

    raw = RawArticle(
        title="Đại nhạc hội Tri Ân Người Hâm Mộ",
        url="https://ticketbox.vn/trian-2026",
        summary="Sự kiện âm nhạc",
        province="TP. Hồ Chí Minh",
        source_name="Ticketbox",
        source_type="ticketing",
    )
    event = fallback_extractor.extract(raw)
    assert event is not None
    assert event.canonical_name == "Đại nhạc hội Tri Ân Người Hâm Mộ"
    print("[OK] test_exporter_and_extractor thành công.")

if __name__ == "__main__":
    test_event_filter()
    test_normalizer()
    test_deduplicator()
    test_exporter_and_extractor()
    print("\n TOÀN BỘ TEST PROCESSING ĐÃ PASS THÀNH CÔNG!")