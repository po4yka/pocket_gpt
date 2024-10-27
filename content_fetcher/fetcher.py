import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional

from firecrawl import FirecrawlApp
from loguru import logger
from sqlalchemy.orm import Session

from config import FIRECRAWL_API_KEY
from models import Article


class FetchErrorType(Enum):
    """Enumeration of possible fetch error types"""

    RATE_LIMIT = auto()
    BLOCKED_URL = auto()
    SOCIAL_MEDIA = auto()
    NO_URL = auto()
    NETWORK_ERROR = auto()
    API_ERROR = auto()
    UNKNOWN = auto()


@dataclass
class FetchError:
    """Class to store information about fetch errors"""

    type: FetchErrorType
    message: str
    details: Optional[str] = None
    response_code: Optional[int] = None
    timestamp: datetime = datetime.now()


class ContentFetcher:
    """
    A class for fetching and saving content from web articles using the Firecrawl SDK.

    Rate Limits:
    - 3,000 pages total
    - 20 /scrape requests per minute
    - 3 /crawl requests per minute
    """

    # Social media domains that are known to be blocked
    SOCIAL_MEDIA_DOMAINS = {
        "twitter.com",
        "x.com",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "tiktok.com",
        "reddit.com",
    }

    def __init__(
        self,
        session: Session,
        min_wait_time: float = 3.0,
    ):
        """Initialize the ContentFetcher with a database session."""
        self.session = session
        self.min_wait_time = min_wait_time
        self.firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

        # Statistics tracking
        self.stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "blocked_urls": 0,
            "social_media_blocked": 0,
            "rate_limited": 0,
            "other_errors": 0,
        }

        # Error tracking
        self.failed_articles: Dict[str, List[FetchError]] = {}

        # Rate limiting state
        self.last_request_time = 0.0

        logger.info("ContentFetcher initialized with Firecrawl SDK")

    def _wait_for_rate_limit(self):
        """Ensure minimum wait time between requests."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_wait_time:
            wait_time = self.min_wait_time - time_since_last_request
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def _log_failure(self, article: Article, error: FetchError):
        """Log a failure for an article."""
        if article.pocket_id not in self.failed_articles:
            self.failed_articles[article.pocket_id] = []

        self.failed_articles[article.pocket_id].append(error)

        error_message = (
            f"Failed to fetch content for article {article.pocket_id}\n"
            f"URL: {article.url}\n"
            f"Title: {article.title}\n"
            f"Error Type: {error.type.name}\n"
            f"Error Message: {error.message}"
        )

        if error.details:
            error_message += f"\nDetails: {error.details}"

        logger.warning(error_message)

    def fetch_and_save_content(self, article: Article) -> bool:
        """Fetch content for a single article and save it to the database."""
        if not article.url:
            error = FetchError(type=FetchErrorType.NO_URL, message="No URL provided for article")
            self._log_failure(article, error)
            return False

        # Wait for rate limit
        self._wait_for_rate_limit()

        try:
            logger.info(f"Fetching content for article: {article.pocket_id}")

            response = self.firecrawl.scrape_url(
                url=article.url,
                params={
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                    "waitFor": 3000,  # Wait 3 seconds for dynamic content
                },
            )

            if not response:
                error = FetchError(type=FetchErrorType.API_ERROR, message="Empty response from API")
                self._log_failure(article, error)
                return False

            # Store the content
            article.content = response.get("markdown", "")
            article.content_html = response.get("html", "")

            # Update metadata
            metadata = response.get("metadata", {})
            if metadata:
                if not article.title and metadata.get("title"):
                    article.title = metadata.get("title")
                article.author = metadata.get("author")
                article.firecrawl_metadata = metadata

            self.session.commit()
            logger.info(f"Content and metadata saved for article: {article.pocket_id}")
            return True

        except Exception as e:
            error_type = FetchErrorType.UNKNOWN
            error_message = str(e)

            # Check for known error messages
            error_str = str(e).lower()
            if "rate limit" in error_str:
                error_type = FetchErrorType.RATE_LIMIT
            elif "url is blocked" in error_str:
                error_type = FetchErrorType.BLOCKED_URL
            elif any(domain in error_str for domain in self.SOCIAL_MEDIA_DOMAINS):
                error_type = FetchErrorType.SOCIAL_MEDIA
            elif "network" in error_str or "connection" in error_str:
                error_type = FetchErrorType.NETWORK_ERROR

            error = FetchError(type=error_type, message=error_message)
            self._log_failure(article, error)

            # Update statistics
            if error_type == FetchErrorType.SOCIAL_MEDIA:
                self.stats["social_media_blocked"] += 1
            elif error_type == FetchErrorType.BLOCKED_URL:
                self.stats["blocked_urls"] += 1
            elif error_type == FetchErrorType.RATE_LIMIT:
                self.stats["rate_limited"] += 1
            else:
                self.stats["other_errors"] += 1

            return False

    def fetch_content_for_all_articles(self) -> None:
        """Fetch content for all articles without content."""
        logger.info("Starting content fetch for all articles without content")

        # Clear previous tracking
        self.failed_articles.clear()
        self.stats = {key: 0 for key in self.stats}

        articles = (
            self.session.query(Article)
            .filter((Article.content.is_(None) | (Article.content == "")) & (Article.url.isnot(None)))
            .all()
        )

        total_articles = len(articles)
        logger.info(f"Found {total_articles} articles without content")

        try:
            for index, article in enumerate(articles, 1):
                logger.info(f"Processing article {index}/{total_articles}: {article.pocket_id}")

                self.stats["total_processed"] += 1

                try:
                    success = self.fetch_and_save_content(article)
                    if success:
                        self.stats["successful"] += 1
                    else:
                        self.stats["failed"] += 1
                except Exception as e:
                    self.stats["failed"] += 1
                    error = FetchError(type=FetchErrorType.UNKNOWN, message=f"Unexpected error: {str(e)}")
                    self._log_failure(article, error)
                    logger.exception(f"Error processing article {article.pocket_id}")
                    continue

        finally:
            # Log final statistics
            logger.info("\nProcessing Complete")
            logger.info("=" * 50)
            logger.info(f"Total processed: {self.stats['total_processed']}")
            logger.info(f"Successful: {self.stats['successful']}")
            logger.info(f"Failed: {self.stats['failed']}")
            logger.info(f"Social media blocked: {self.stats['social_media_blocked']}")
            logger.info(f"Other blocked URLs: {self.stats['blocked_urls']}")
            logger.info(f"Rate limited: {self.stats['rate_limited']}")
            logger.info(f"Other errors: {self.stats['other_errors']}")

            if self.failed_articles:
                logger.warning("\nFailed Articles:")
                for pocket_id, errors in self.failed_articles.items():
                    logger.warning(f"\nArticle {pocket_id}:")
                    for error in errors:
                        logger.warning(f"- {error.type.name}: {error.message}")

    def get_processing_stats(self) -> Dict[str, int]:
        """Get current processing statistics."""
        return self.stats.copy()
