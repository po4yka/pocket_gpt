from firecrawl import FirecrawlApp
from loguru import logger

from config import FIRECRAWL_API_KEY


class ContentFetcher:
    def __init__(self):
        self.app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

    def fetch_content(self, url):
        logger.info(f"Fetching content for URL: {url}")
        try:
            scrape_result = self.app.scrape_url(url, params={"formats": ["markdown", "html"]})
            content = scrape_result.get("markdown") or scrape_result.get("html")
            if not content:
                logger.warning(f"No content found for URL: {url}")
                return None
            return content
        except Exception as e:
            logger.error(f"Error fetching content for {url}: {e}")
            return None
