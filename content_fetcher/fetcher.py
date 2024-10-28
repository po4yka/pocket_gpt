import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Union

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
    """A class for fetching and saving content from web articles using the Firecrawl SDK."""

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
        self.session = session
        self.min_wait_time = min_wait_time
        self.firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        self.stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "blocked_urls": 0,
            "social_media_blocked": 0,
            "rate_limited": 0,
            "other_errors": 0,
        }
        self.failed_articles: Dict[str, List[FetchError]] = {}
        self.last_request_time = 0.0

    def _log_failure(self, article: Article, error: FetchError) -> None:
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

    def _sanitize_text(self, text: Optional[str]) -> Optional[str]:
        """Sanitize text content for database storage."""
        if text is None:
            return None
        # Convert to string and handle any special characters
        return str(text).encode("utf-8", errors="ignore").decode("utf-8")

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize metadata dictionary for JSON storage."""
        # Remove any problematic values and ensure all values are JSON-serializable
        cleaned_metadata = {}
        for key, value in metadata.items():
            try:
                # Test if the value is JSON serializable
                json.dumps({key: value})
                cleaned_metadata[key] = value
            except (TypeError, ValueError):
                # If not serializable, convert to string
                cleaned_metadata[key] = str(value)
        return cleaned_metadata

    def _sanitize_authors(self, authors: Union[List[str], str, None]) -> Optional[str]:
        """Sanitize and format author information."""
        if not authors:
            return None
        if isinstance(authors, list):
            return ", ".join(str(author) for author in authors)
        return str(authors)

    def fetch_and_save_content(self, article: Article) -> bool:
        """Fetch content for a single article and save it to the database."""
        if not article.url:
            error = FetchError(type=FetchErrorType.NO_URL, message="No URL provided for article")
            self._log_failure(article, error)
            return False

        try:
            logger.info(f"Fetching content for article: {article.pocket_id}")

            response = self.firecrawl.scrape_url(
                url=article.url,
                params={
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                    "waitFor": 3000,
                },
            )

            if not response:
                error = FetchError(type=FetchErrorType.API_ERROR, message="Empty response from API")
                self._log_failure(article, error)
                return False

            # Sanitize the content before saving
            article.content = self._sanitize_text(response.get("markdown", ""))
            article.content_html = self._sanitize_text(response.get("html", ""))

            # Update metadata
            metadata = response.get("metadata", {})
            if metadata:
                if not article.title and metadata.get("title"):
                    article.title = self._sanitize_text(metadata.get("title"))
                article.author = self._sanitize_authors(metadata.get("author"))
                # Sanitize and store metadata
                article.firecrawl_metadata = self._sanitize_metadata(metadata)

            try:
                self.session.commit()
                logger.info(f"Content and metadata saved for article: {article.pocket_id}")
                return True
            except Exception as e:
                self.session.rollback()
                logger.error(f"Database error while saving article {article.pocket_id}: {e}")
                raise

        except Exception as e:
            error_type = FetchErrorType.UNKNOWN
            error_message = str(e)

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

            if error_type == FetchErrorType.SOCIAL_MEDIA:
                self.stats["social_media_blocked"] += 1
            elif error_type == FetchErrorType.BLOCKED_URL:
                self.stats["blocked_urls"] += 1
            elif error_type == FetchErrorType.RATE_LIMIT:
                self.stats["rate_limited"] += 1
            else:
                self.stats["other_errors"] += 1

            return False
