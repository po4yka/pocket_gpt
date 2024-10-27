import requests
from loguru import logger
from sqlalchemy.orm import Session

from config import FIRECRAWL_API_KEY
from models import Article


class ContentFetcher:
    """
    A class for fetching and saving content from web articles using the Firecrawl API.

    This class provides methods to fetch content for individual articles or for all
    articles in the database that don't have content yet.

    Attributes:
        session (Session): SQLAlchemy session for database operations.
        api_url (str): The URL of the Firecrawl API endpoint.
        headers (dict): HTTP headers for API requests, including authentication.
    """

    def __init__(self, session: Session):
        """
        Initialize the ContentFetcher with a database session.

        Args:
            session (Session): SQLAlchemy session for database operations.
        """
        self.session = session
        self.api_url = "https://api.firecrawl.dev/v1/scrape"
        self.headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
        }
        logger.info("ContentFetcher initialized")

    def fetch_and_save_content(self, article: Article) -> bool:
        """
        Fetch content for a single article and save it to the database.

        This method sends a request to the Firecrawl API to scrape the article's content
        and metadata. It then saves this information to the provided Article object.

        Args:
            article (Article): The Article object to fetch content for.

        Returns:
            bool: True if content was successfully fetched and saved, False otherwise.
        """
        try:
            logger.info(f"Fetching content for article: {article.pocket_id}")

            payload = {
                "url": article.url,
                "formats": ["markdown", "html"],
                "onlyMainContent": False,
                "timeout": 30000,
                "actions": [{"type": "wait", "milliseconds": 3000}],
                "includeMetadata": True,
            }

            logger.debug(f"Sending request to Firecrawl API for article: {article.pocket_id}")
            response = requests.post(self.api_url, json=payload, headers=self.headers)
            response.raise_for_status()
            scrape_result = response.json()

            if scrape_result:
                logger.debug(f"Content received for article: {article.pocket_id}")
                article.content = scrape_result.get("markdown", "")
                article.content_html = scrape_result.get("html", "")
                article.title = scrape_result.get("title", article.title)

                # Store all metadata in the firecrawl_metadata field
                article.firecrawl_metadata = scrape_result

                # Extract and store additional metadata fields
                article.author = scrape_result.get("author")
                article.published_date = scrape_result.get("publishedDate")
                article.word_count = scrape_result.get("wordCount")
                article.estimated_reading_time = scrape_result.get("estimatedReadingTime")

                self.session.commit()
                logger.info(f"Content and metadata saved for article: {article.pocket_id}")
                return True
            else:
                logger.warning(f"No content fetched for article: {article.pocket_id}")
                return False
        except requests.RequestException as e:
            logger.error(f"API request error for article {article.pocket_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error processing article {article.pocket_id}: {e}")
            return False

    def fetch_content_for_all_articles(self) -> None:
        """
        Fetch content for all articles in the database that don't have content yet.

        This method queries the database for all articles without content and attempts
        to fetch and save content for each of them.
        """
        logger.info("Starting content fetch for all articles without content")
        articles = self.session.query(Article).filter(Article.content.is_(None)).all()
        logger.info(f"Found {len(articles)} articles without content")

        for index, article in enumerate(articles, 1):
            logger.info(f"Processing article {index}/{len(articles)}: {article.pocket_id}")
            success = self.fetch_and_save_content(article)
            if success:
                logger.info(f"Successfully fetched content for article: {article.pocket_id}")
            else:
                logger.warning(f"Failed to fetch content for article: {article.pocket_id}")

        logger.info("Completed content fetch for all articles")
