import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
import warnings

from bs4 import BeautifulSoup
import feedparser
import requests
from urllib3.exceptions import InsecureRequestWarning
import yaml

# Tắt cảnh báo SSL không an toàn khi truy cập các cổng .gov.vn cũ
warnings.simplefilter("ignore", InsecureRequestWarning)

# Định vị đường dẫn config an toàn
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "sources.yaml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}
TIMEOUT = 15


def load_config(file_path: Path) -> list:
    """Đọc danh sách sources từ file YAML."""
    if not file_path.exists():
        print(f"[!] Không tìm thấy file cấu hình tại: {file_path}")
        sys.exit(1)
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", [])


def extract_title_and_link(item_el, base_url: str):
    """
    Trích xuất an toàn tiêu đề và link từ thẻ bài viết:
    Bỏ qua thẻ <a> bọc ảnh thumbnail (text rỗng) để tránh tiêu đề bị trắng.
    """
    # 1. Thử tìm thẻ heading trước (h1, h2, h3, h4)
    heading_a = item_el.select_one("h1 a, h2 a, h3 a, h4 a, .title a, a.title")
    if heading_a and heading_a.get_text(strip=True):
        title = heading_a.get_text(strip=True)
        link = heading_a.get("href", "").strip()
        return title, urljoin(base_url, link)

    # 2. Duyệt qua tất cả thẻ a để tìm thẻ có text thực tế (> 10 ký tự)
    for a in item_el.find_all("a", href=True):
        text = a.get_text(strip=True) or a.get("title", "").strip()
        if len(text) >= 10:
            return text, urljoin(base_url, a["href"].strip())

    # 3. Fallback lấy bất kỳ thẻ a nào
    first_a = item_el.find("a", href=True)
    if first_a:
        title = first_a.get_text(strip=True) or first_a.get("title", "Không có tiêu đề")
        return title, urljoin(base_url, first_a["href"].strip())

    return item_el.get_text(strip=True)[:50], ""


def test_sources():
    sources = load_config(CONFIG_PATH)
    if not sources:
        print("[!] Không tìm thấy danh sách 'sources' nào trong file cấu hình!")
        return

    print(f"\n===== ĐANG KIỂM TRA TỔNG CỘNG {len(sources)} NGUỒN CÀO =====\n")

    for src in sources:
        name = src.get("name", "Unknown")
        url = src.get("url")
        s_type = src.get("source_type", "")
        p_type = src.get("parser_type", "")
        province = src.get("province", "ALL")
        prefix = f"[{province}] {name}"

        if not url:
            print(f"[x] [SKIP] {prefix} -> Thiếu trường 'url'!")
            continue

        # =========================================================
        # 1. Kiểm tra nguồn dạng RSS Feed
        # =========================================================
        if s_type == "rss" or p_type == "rss":
            try:
                res = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
                res.raise_for_status()
                feed = feedparser.parse(res.content)

                if feed.bozo and len(feed.entries) == 0:
                    print(f"[-] [RSS LOI]   {prefix} -> Sai định dạng XML: {feed.bozo_exception}")
                elif len(feed.entries) == 0:
                    print(f"[!] [RSS TRONG] {prefix} -> Phản hồi 200 nhưng không có bài viết (0 entries)")
                else:
                    sample = feed.entries[0].get("title", "Không rõ tiêu đề")
                    print(f"[+] [RSS OK]     {prefix} -> {len(feed.entries)} bài. (Bài mới: {sample[:45]}...)")
            except Exception as e:
                print(f"[x] [RSS FAIL]   {prefix} -> Lỗi: {e}")

        # =========================================================
        # 2. Kiểm tra nguồn Ticketbox / API JSON
        # =========================================================
        elif p_type in ["api_json", "dynamic_js_or_internal_api"] or s_type == "ticketing":
            try:
                req_headers = HEADERS.copy()
                params = {}
                if "ticketbox.vn" in url:
                    req_headers["Referer"] = "https://ticketbox.vn/"
                    params = {"at": "this-month"}

                res = requests.get(url, headers=req_headers, params=params, timeout=TIMEOUT, verify=False)
                res.raise_for_status()
                data = res.json()

                items = []
                if isinstance(data, dict):
                    data_body = data.get("data", {})
                    if isinstance(data_body, dict):
                        items = data_body.get("results") or data_body.get("items") or []
                    elif isinstance(data_body, list):
                        items = data_body
                elif isinstance(data, list):
                    items = data

                if not items:
                    print(f"[!] [API TRONG] {prefix} -> Kết nối 200 OK nhưng mảng sự kiện rỗng.")
                else:
                    sample_name = items[0].get("name") or items[0].get("title") or "Sự kiện không tên"
                    sample_time = items[0].get("day") or items[0].get("startDate") or "N/A"
                    print(f"[+] [API OK]     {prefix} -> Lấy được {len(items)} sự kiện. (Mẫu: {str(sample_name)[:35]} | Thời gian: {sample_time})")
            except requests.exceptions.JSONDecodeError:
                print(f"[x] [API FAIL]   {prefix} -> Trả về HTML thay vì JSON (có thể do bị chặn bot hoặc sai endpoint API)")
            except Exception as e:
                print(f"[x] [API FAIL]   {prefix} -> Lỗi: {e}")

        # =========================================================
        # 3. Kiểm tra nguồn HTML Web / Cổng thông tin
        # =========================================================
        else:
            try:
                res = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")

                # Lấy selector từ config
                selectors_cfg = src.get("selectors", {})
                custom_selector = selectors_cfg.get("container") if isinstance(selectors_cfg, dict) else None
                selector = custom_selector or "article, .news-item, .item-news, .story, .item, a[href*='tin-tuc']"

                articles = soup.select(selector)
                if not articles:
                    print(f"[!] [WEB TRONG] {prefix} -> 200 OK nhưng selector `{selector}` không bắt được phần tử nào.")
                else:
                    # In thử tiêu đề mẫu để xác nhận không bị nuốt chữ
                    sample_title, sample_link = extract_title_and_link(articles[0], url)
                    print(f"[+] [WEB OK]     {prefix} -> Phát hiện {len(articles)} bài viết.")
                    print(f"                 └── Mẫu: \"{sample_title[:50]}...\" ({sample_link[:45]}...)")
            except Exception as e:
                print(f"[x] [WEB FAIL]   {prefix} -> Lỗi kết nối/HTTP: {e}")


if __name__ == "__main__":
    test_sources()