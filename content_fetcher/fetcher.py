import requests
from bs4 import BeautifulSoup
from firecrawl import FirecrawlApp
from loguru import logger

from config import FIRECRAWL_API_KEY


class ContentFetcher:
    def __init__(self):
        self.app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

    def fetch_content(self, url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching content: {e}")
            return None

    def extract_original_url(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")
        original_link = soup.find("a", class_="original_url")
        return original_link["href"] if original_link else None

    def extract_title(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")
        title = soup.find("h1", class_="reader_title")
        return title.text.strip() if title else None
