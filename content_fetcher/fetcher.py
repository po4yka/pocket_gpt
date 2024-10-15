import requests
from loguru import logger
from sqlalchemy.orm import Session

from config import FIRECRAWL_API_KEY
from models import Article


class ContentFetcher:
    def __init__(self, session: Session):
        self.session = session
        self.api_url = "https://api.firecrawl.dev/v1/scrape"
        self.headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}

    def fetch_and_save_content(self, article: Article):
        try:
            logger.info(f"Fetching content for article: {article.pocket_id}")

            payload = {
                "url": article.url,
                "formats": ["markdown", "html"],
                "onlyMainContent": True,
                "timeout": 30000,
                "actions": [{"type": "wait", "milliseconds": 3000}],
            }

            response = requests.post(self.api_url, json=payload, headers=self.headers)
            response.raise_for_status()
            scrape_result = response.json()

            if scrape_result:
                article.content = scrape_result.get("markdown", "")
                article.content_html = scrape_result.get("html", "")
                article.title = scrape_result.get("title", article.title)

                article.firecrawl_metadata = scrape_result

                self.session.commit()
                logger.info(f"Content and metadata saved for article: {article.pocket_id}")
                return True
            else:
                logger.warning(f"No content fetched for article: {article.pocket_id}")
                return False
        except requests.RequestException as e:
            logger.error(f"Error fetching content for article {article.pocket_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error for article {article.pocket_id}: {e}")
            return False

    def fetch_content_for_all_articles(self):
        articles = self.session.query(Article).filter(Article.content.is_(None)).all()
        for article in articles:
            self.fetch_and_save_content(article)
