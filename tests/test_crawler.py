import sys
from pathlib import Path
import pytest
import yaml

# Thêm thư mục gốc vào sys.path để import các module trong src/ hoặc crawler/
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

from crawler.fetcher import Fetcher
from crawler.html_cleaner import HTMLCleaner
from crawler.parsers.rss_parser import RSSParser
from crawler.parsers.api_parser import APIParser
from crawler.parsers.html_parser import HTMLParser
from crawler.engine import CrawlerEngine


# ==========================================================
# 1. UNIT TEST CHO TỪNG COMPONENT
# ==========================================================

def test_html_cleaner():
    """Kiểm tra HTMLCleaner lọc sạch script, style, nav và trích xuất text."""
    sample_html = """
    <html>
        <head><title>Test Title</title><style>.hidden { display: none; }</style></head>
        <body>
            <nav><a href="/home">Trang chủ</a></nav>
            <article class="content-detail">
                <h1>Lễ hội Ok Om Bok Trà Vinh 2026</h1>
                <p>Lễ hội sẽ diễn ra tại ao Bà Om với nhiều hoạt động đua ghe Ngo sôi nổi.</p>
            </article>
            <script>console.log("analytics");</script>
            <footer>Bản quyền thuộc về báo</footer>
        </body>
    </html>
    """
    cleaned_text = HTMLCleaner.clean_html(sample_html)
    assert "Lễ hội Ok Om Bok Trà Vinh 2026" in cleaned_text
    assert "ao Bà Om" in cleaned_text
    assert "console.log" not in cleaned_text
    assert "Trang chủ" not in cleaned_text
    assert "Bản quyền" not in cleaned_text
    print("\n[OK] test_html_cleaner thành công.")


def test_rss_parser():
    """Kiểm tra RSSParser bóc tách đúng cấu trúc từ XML feed mẫu."""
    sample_xml = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
        <channel>
            <title>Tin tuc test</title>
            <item>
                <title>Hội xuân Núi Bà Đen Tây Ninh</title>
                <link>https://example.com/hoi-xuan-tay-ninh</link>
                <description>Hàng vạn du khách đổ về Tây Ninh chiêm bái tượng Phật Bà.</description>
                <pubDate>Mon, 05 Oct 2026 07:00:00 +0700</pubDate>
            </item>
        </channel>
    </rss>
    """.encode("utf-8")
    source_meta = {"name": "Test RSS", "province": "Tây Ninh"}
    results = RSSParser.parse(sample_xml, source_meta)

    assert len(results) == 1
    item = results[0]
    assert item["title"] == "Hội xuân Núi Bà Đen Tây Ninh"
    assert item["url"] == "https://example.com/hoi-xuan-tay-ninh"
    assert item["province"] == "Tây Ninh"
    assert item["source_type"] == "rss"
    print("[OK] test_rss_parser thành công.")


def test_api_parser_ticketbox():
    """Kiểm tra APIParser parse đúng format data -> results của Ticketbox."""
    sample_json = {
        "code": 200,
        "message": "Success",
        "data": {
            "results": [
                {
                    "id": 101,
                    "name": "Đại nhạc hội Countdown TP.HCM",
                    "day": "2026-12-31T20:00:00Z",
                    "price": 250000,
                    "deeplink": "https://ticketbox.vn/countdown-2026"
                }
            ]
        }
    }
    source_meta = {"name": "Ticketbox", "province": "TP. Hồ Chí Minh"}
    results = APIParser.parse_ticketbox(sample_json, source_meta)

    assert len(results) == 1
    ev = results[0]
    assert ev["title"] == "Đại nhạc hội Countdown TP.HCM"
    assert ev["url"] == "https://ticketbox.vn/countdown-2026"
    assert ev["province"] == "TP. Hồ Chí Minh"
    assert ev["source_type"] == "ticketing"
    print("[OK] test_api_parser_ticketbox thành công.")


def test_fetcher_real_url():
    """Kiểm tra Fetcher thực hiện request với user-agent và timeout hợp lệ."""
    fetcher = Fetcher(timeout=5)
    resp = fetcher.get("https://httpbin.org/get")
    assert resp is not None
    assert resp.status_code == 200
    print("[OK] test_fetcher_real_url thành công.")


# ==========================================================
# 2. INTEGRATION TEST: CHẠY THỰC TẾ ENGINE TRÊN SOURCES.YAML
# ==========================================================

def test_engine_crawl_real_sources():
    """Chạy Engine cào thử từ file config/sources.yaml để kiểm tra kết nối thật."""
    config_file = BASE_DIR / "config" / "sources.yaml"
    if not config_file.exists():
        pytest.skip("Chưa có file config/sources.yaml, bỏ qua test tích hợp.")

    with open(config_file, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
        sources = cfg.get("sources", [])

    assert len(sources) >= 5, "Cần cấu hình ít nhất 5 nguồn tin theo yêu cầu đề bài!"

    engine = CrawlerEngine()
    
    # Lấy thử 2 nguồn đầu tiên đại diện để test nhanh mà không làm nghẽn mạng
    sample_sources = sources[:3]
    total_crawled = []

    print(f"\n===== CHẠY TEST ENGINE THỰC TẾ TRÊN {len(sample_sources)} NGUỒN MẪU =====")
    for src in sample_sources:
        items = engine.crawl_source(src)
        print(f" -> Nguồn [{src.get('name')}]: Thu được {len(items)} tin.")
        total_crawled.extend(items)

    assert len(total_crawled) > 0, "Không thu thập được tin nào từ các nguồn mẫu!"
    
    first_item = total_crawled[0]
    # Kiểm tra tính toàn vẹn của dữ liệu thu thập
    assert "title" in first_item and first_item["title"] != ""
    assert "url" in first_item and first_item["url"].startswith("http")
    assert "raw_text" in first_item
    assert "province" in first_item

    print(f"[OK] test_engine_crawl_real_sources thành công: Thu thập tổng {len(total_crawled)} tin.")


if __name__ == "__main__":
    # Cho phép chạy trực tiếp bằng python tests/test_crawler.py
    test_html_cleaner()
    test_rss_parser()
    test_api_parser_ticketbox()
    test_fetcher_real_url()
    test_engine_crawl_real_sources()
    print("\n TOÀN BỘ TEST CRAWLER ĐÃ PASS THÀNH CÔNG!")