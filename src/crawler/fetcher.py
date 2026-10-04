import logging
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, timeout: int = 15, max_retries: int = 3):
        self.timeout = timeout
        self.session = requests.Session()

        # Cấu hình retry tự động khi gặp lỗi mạng tạm thời hoặc 5xx
        retries = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def get(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Optional[requests.Response]:
        req_headers = self.default_headers.copy()
        if headers:
            req_headers.update(headers)

        try:
            response = self.session.get(url, params=params, headers=req_headers, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Lỗi khi tải URL {url}: {e}")
            return None