import re
from bs4 import BeautifulSoup


class HTMLCleaner:
    @staticmethod
    def clean_html(html_content: str) -> str:
        """Lọc bỏ script, css, menu, quảng cáo và trích xuất text thuần sạch."""
        if not html_content:
            return ""

        soup = BeautifulSoup(html_content, "html.parser")

        # Xóa các thẻ rác không chứa nội dung chính
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript"]):
            tag.decompose()

        # Ưu tiên lấy vùng nội dung chính nếu có class chuẩn bài viết
        main_content = soup.select_one(
            "article, .fck_detail, .detail-content, .content-detail, .post-content, .entry-content, #main-content"
        )
        target = main_content if main_content else soup.body or soup

        text = target.get_text(separator=" ", strip=True)
        # Chuẩn hóa khoảng trắng dư thừa
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def extract_article_urls(html_content: str, base_url: str, container_selector: str = None) -> list:
        """Lấy danh sách link bài viết từ trang danh mục."""
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        urls = set()

        if container_selector:
            elements = soup.select(container_selector)
        else:
            elements = soup.select("article, .news-item, .item-news, .story, .item")

        for el in elements:
            # Tìm thẻ link <a>
            a_tag = el if el.name == "a" else el.find("a", href=True)
            if a_tag and a_tag.get("href"):
                href = a_tag["href"].strip()
                # Chuyển đổi link tương đối sang link tuyệt đối
                if href.startswith("/"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                if href.startswith("http"):
                    urls.add(href)

        return list(urls)