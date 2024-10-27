import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

import requests
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
    A class for fetching and saving content from web articles using the Firecrawl API.

    Rate Limits:
    - 3,000 pages total
    - 20 /scrape requests per minute
    - 3 /crawl requests per minute

    Attributes:
        session (Session): SQLAlchemy session for database operations.
        api_url (str): The URL of the Firecrawl API endpoint.
        headers (dict): HTTP headers for API requests, including authentication.
        max_retries (int): Maximum number of retries for rate-limited requests.
        min_wait_time (float): Minimum time to wait between requests in seconds.
        requests_per_minute (int): Maximum number of requests allowed per minute.
        total_requests_limit (int): Maximum total number of requests allowed.
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
        max_retries: int = 3,
        min_wait_time: float = 3.0,
        requests_per_minute: int = 20,
        total_requests_limit: int = 3000,
    ):
        """Initialize the ContentFetcher with a database session."""
        self.session = session
        self.api_url = "https://api.firecrawl.dev/v1/scrape"
        self.headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
        }
        self.max_retries = max_retries
        self.min_wait_time = min_wait_time
        self.requests_per_minute = requests_per_minute
        self.total_requests_limit = total_requests_limit

        # Rate limiting state
        self.last_request_time = 0.0
        self.request_count = 0
        self.minute_request_count = 0
        self.minute_start_time = time.time()

        # Error tracking
        self.failed_articles: Dict[str, List[FetchError]] = {}

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

        logger.info(
            f"ContentFetcher initialized with rate limits: "
            f"{requests_per_minute} requests/minute, "
            f"{total_requests_limit} total requests"
        )

    def _wait_for_rate_limit(self):
        """Wait if necessary to comply with rate limits."""
        current_time = time.time()

        # Check total request limit
        if self.request_count >= self.total_requests_limit:
            logger.error(f"Total request limit of {self.total_requests_limit} reached")
            raise Exception("Total request limit reached")

        # Reset minute counter if a minute has passed
        if current_time - self.minute_start_time >= 60:
            self.minute_request_count = 0
            self.minute_start_time = current_time

        # Check minute rate limit
        if self.minute_request_count >= self.requests_per_minute:
            wait_time = 60 - (current_time - self.minute_start_time)
            if wait_time > 0:
                logger.info(f"Rate limit approaching. Waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)
                self.minute_request_count = 0
                self.minute_start_time = time.time()

        # Ensure minimum wait time between requests
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_wait_time:
            wait_time = self.min_wait_time - time_since_last_request
            time.sleep(wait_time)

    def _update_rate_limit_counters(self):
        """Update the rate limit counters after a successful request."""
        self.request_count += 1
        self.minute_request_count += 1
        self.last_request_time = time.time()

    def _parse_rate_limit_response(self, response_text: str) -> Tuple[float, datetime]:
        """Parse rate limit information from the API response."""
        try:
            data = json.loads(response_text)
            error_msg = data.get("error", "")

            # Extract requests remaining from error message if available
            remaining = None
            if "Remaining (req/min):" in error_msg:
                remaining_str = error_msg.split("Remaining (req/min):")[1].split(",")[0].strip()
                remaining = int(remaining_str)

            # Try to extract reset time from the error message
            if "resets at" in error_msg:
                reset_time_str = error_msg.split("resets at ")[1].split(" GMT")[0]
                reset_time = datetime.strptime(reset_time_str, "%a %b %d %Y %H:%M:%S")

                # Calculate wait time in seconds
                now = datetime.now()
                wait_seconds = max((reset_time - now).total_seconds(), self.min_wait_time)

                logger.info(f"Rate limit info - Remaining: {remaining}, Reset time: {reset_time}")
                return wait_seconds, reset_time
            else:
                # Default wait time if we can't parse the reset time
                return self.min_wait_time, datetime.now()

        except (json.JSONDecodeError, ValueError, IndexError) as e:
            logger.warning(f"Failed to parse rate limit response: {e}")
            return self.min_wait_time, datetime.now()

    def _handle_rate_limit(self, response: requests.Response, retry_count: int) -> Optional[float]:
        """Handle rate limit response and determine wait time."""
        if retry_count >= self.max_retries:
            logger.error(f"Max retries ({self.max_retries}) exceeded for rate limit handling")
            return None

        wait_time, reset_time = self._parse_rate_limit_response(response.text)

        # Apply exponential backoff with a minimum wait time
        wait_time = max(wait_time * (2**retry_count), self.min_wait_time)

        logger.warning(
            f"Rate limit encountered. Retry {retry_count + 1}/{self.max_retries}. "
            f"Waiting {wait_time:.2f} seconds. "
            f"Rate limit resets at {reset_time}"
        )

        return wait_time

    def _is_social_media_url(self, url: Optional[str]) -> bool:
        """
        Check if a URL is from a social media domain.

        Args:
            url (Optional[str]): The URL to check, can be None

        Returns:
            bool: True if the URL is from a social media domain, False otherwise
        """
        if not url:
            return False

        try:
            # Extract domain from URL
            domain = re.search(r"(?:https?://)?(?:www\.)?([^/]+)", url.lower())
            if domain and domain.group(1):
                return any(sm in domain.group(1) for sm in self.SOCIAL_MEDIA_DOMAINS)
        except Exception:
            return False
        return False

    def _handle_forbidden_error(self, article: Article, response: requests.Response) -> FetchErrorType:
        """Handle 403 Forbidden errors and determine the specific type."""
        try:
            error_data = response.json()
            error_message = error_data.get("error", "")

            if "URL is blocked" in error_message:
                if self._is_social_media_url(article.url):
                    self.stats["social_media_blocked"] += 1
                    return FetchErrorType.SOCIAL_MEDIA
                else:
                    self.stats["blocked_urls"] += 1
                    return FetchErrorType.BLOCKED_URL

        except (json.JSONDecodeError, AttributeError):
            pass

        return FetchErrorType.API_ERROR

    def _log_failure(self, article: Article, error: FetchError):
        """Log a failure for an article with enhanced error tracking."""
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

        if error.response_code:
            error_message += f"\nResponse Code: {error.response_code}"

        logger.warning(error_message)

    def _generate_failure_report(self) -> str:
        """Generate a detailed summary report of all failures."""
        if not self.failed_articles:
            return "No failures occurred during processing."

        report = [
            "Failure Report:",
            "=" * 50,
            "\nStatistics:",
            f"Total Processed: {self.stats['total_processed']}",
            f"Successful: {self.stats['successful']}",
            f"Failed: {self.stats['failed']}",
            f"Social Media Blocked: {self.stats['social_media_blocked']}",
            f"Other Blocked URLs: {self.stats['blocked_urls']}",
            f"Rate Limited: {self.stats['rate_limited']}",
            f"Other Errors: {self.stats['other_errors']}",
            "\nDetailed Failures:",
            "=" * 50,
        ]

        # Group failures by error type
        failures_by_type: Dict[FetchErrorType, List[Tuple[str, FetchError]]] = {}
        for pocket_id, errors in self.failed_articles.items():
            for error in errors:
                if error.type not in failures_by_type:
                    failures_by_type[error.type] = []
                failures_by_type[error.type].append((pocket_id, error))

        # Report failures grouped by type
        for error_type, failures in failures_by_type.items():
            report.append(f"\n{error_type.name} Failures:")
            report.append("-" * 50)

            for pocket_id, error in failures:
                article = self.session.query(Article).filter(Article.pocket_id == pocket_id).first()
                report.append(f"\nArticle ID: {pocket_id}")
                report.append(f"URL: {article.url if article else 'Unknown'}")
                report.append(f"Title: {article.title if article else 'Unknown'}")
                report.append(f"Error: {error.message}")
                if error.details:
                    report.append(f"Details: {error.details}")
                if error.response_code:
                    report.append(f"Response Code: {error.response_code}")
                report.append("-" * 30)

        return "\n".join(report)

    def fetch_and_save_content(self, article: Article) -> bool:
        """Fetch content for a single article and save it to the database."""
        if not article.url:
            error = FetchError(type=FetchErrorType.NO_URL, message="No URL provided for article")
            self._log_failure(article, error)
            return False

        # Pre-check for social media URLs - article.url is guaranteed to be non-None here
        if article.url and self._is_social_media_url(article.url):
            error = FetchError(
                type=FetchErrorType.SOCIAL_MEDIA,
                message="Social media URL detected - skipping to avoid rate limit consumption",
                details=f"Domain is in blocked list: {article.url}",
            )
            self._log_failure(article, error)
            return False

        retry_count = 0
        while retry_count <= self.max_retries:
            try:
                self._wait_for_rate_limit()

                logger.info(f"Fetching content for article: {article.pocket_id} (Attempt {retry_count + 1})")

                payload = {
                    "url": article.url,
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                    "timeout": 30000,
                    "actions": [{"type": "wait", "milliseconds": 3000}],
                    "waitFor": 0,
                }

                logger.debug(f"Sending request to Firecrawl API for article: {article.pocket_id}")
                response = requests.post(self.api_url, json=payload, headers=self.headers)

                if response.status_code == 429:  # Too Many Requests
                    self.stats["rate_limited"] += 1
                    error = FetchError(
                        type=FetchErrorType.RATE_LIMIT,
                        message="Rate limit exceeded",
                        details=response.text,
                        response_code=response.status_code,
                    )
                    self._log_failure(article, error)

                    wait_time = self._handle_rate_limit(response, retry_count)
                    if wait_time is None:
                        return False
                    time.sleep(wait_time)
                    retry_count += 1
                    continue

                elif response.status_code == 403:  # Forbidden
                    error_type = self._handle_forbidden_error(article, response)
                    error = FetchError(
                        type=error_type,
                        message="Access forbidden by API",
                        details=response.text,
                        response_code=response.status_code,
                    )
                    self._log_failure(article, error)
                    return False  # Don't retry for forbidden errors

                response.raise_for_status()
                self._update_rate_limit_counters()

                result = response.json()
                if not result.get("success"):
                    error = FetchError(
                        type=FetchErrorType.API_ERROR, message="API returned unsuccessful response", details=str(result)
                    )
                    self._log_failure(article, error)
                    return False

                data = result.get("data", {})
                if data:
                    logger.debug(f"Content received for article: {article.pocket_id}")

                    # Store the markdown content
                    article.content = data.get("markdown", "")

                    # Store the HTML content
                    article.content_html = data.get("html", "")

                    # Update metadata fields
                    metadata = data.get("metadata", {})
                    if metadata:
                        # Update title if not already set
                        if not article.title and metadata.get("title"):
                            article.title = metadata.get("title")

                        # Store author if available
                        article.author = metadata.get("author")

                        # Store all metadata in the firecrawl_metadata field
                        article.firecrawl_metadata = metadata

                    self.session.commit()
                    logger.info(
                        f"Content and metadata saved for article: {article.pocket_id} "
                        f"(Total requests: {self.request_count}/{self.total_requests_limit})"
                    )
                    return True
                else:
                    error = FetchError(
                        type=FetchErrorType.API_ERROR,
                        message="No content data received",
                        details="API response successful but no content returned",
                    )
                    self._log_failure(article, error)
                    return False

            except requests.RequestException as e:
                error_type = FetchErrorType.NETWORK_ERROR
                response_text = None
                response_code = None

                if e.response is not None:
                    response_text = e.response.text
                    response_code = e.response.status_code

                    if e.response.status_code == 403:
                        error_type = self._handle_forbidden_error(article, e.response)
                    elif e.response.status_code == 429:
                        error_type = FetchErrorType.RATE_LIMIT

                error = FetchError(type=error_type, message=str(e), details=response_text, response_code=response_code)
                self._log_failure(article, error)

                if error_type == FetchErrorType.RATE_LIMIT:
                    if e.response and e.response.status_code == 429:
                        wait_time = self._handle_rate_limit(e.response, retry_count)
                        if wait_time is None:
                            return False
                        time.sleep(wait_time)
                        retry_count += 1
                        continue

                self.stats["other_errors"] += 1
                return False

            except Exception as e:
                error = FetchError(type=FetchErrorType.UNKNOWN, message=f"Unexpected error: {str(e)}")
                self._log_failure(article, error)
                self.stats["other_errors"] += 1
                return False

        return False

    def fetch_content_for_all_articles(self) -> None:
        """
        Fetch content for all articles in the database that don't have content yet.
        Handles failures gracefully and continues processing remaining articles.
        """
        logger.info("Starting content fetch for all articles without content")

        # Clear previous failure tracking
        self.failed_articles.clear()

        # Reset statistics
        self.stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "blocked_urls": 0,
            "social_media_blocked": 0,
            "rate_limited": 0,
            "other_errors": 0,
        }

        articles = (
            self.session.query(Article)
            .filter((Article.content.is_(None) | (Article.content == "")) & (Article.url.isnot(None)))
            .all()
        )

        total_articles = len(articles)
        if total_articles > self.total_requests_limit - self.request_count:
            logger.warning(
                f"Not enough requests available. Need {total_articles} but only "
                f"{self.total_requests_limit - self.request_count} remaining."
            )

        logger.info(f"Found {total_articles} articles without content")

        try:
            for index, article in enumerate(articles, 1):
                if self.request_count >= self.total_requests_limit:
                    logger.warning(
                        f"Total request limit reached ({self.total_requests_limit}). "
                        f"Stopping processing after {index} articles."
                    )
                    break

                logger.info(
                    f"Processing article {index}/{total_articles}: {article.pocket_id} "
                    f"(Total requests: {self.request_count}/{self.total_requests_limit})"
                )

                self.stats["total_processed"] += 1

                if not article.url:
                    error = FetchError(type=FetchErrorType.NO_URL, message="No URL available")
                    self._log_failure(article, error)
                    self.stats["failed"] += 1
                    continue

                try:
                    success = self.fetch_and_save_content(article)
                    if success:
                        self.stats["successful"] += 1
                        logger.info(
                            f"Successfully fetched content for article: {article.pocket_id} "
                            f"({self.stats['successful']} successes / "
                            f"{self.stats['failed']} failures)"
                        )
                    else:
                        self.stats["failed"] += 1

                except Exception as e:
                    self.stats["failed"] += 1
                    error = FetchError(
                        type=FetchErrorType.UNKNOWN, message=f"Unexpected error during processing: {str(e)}"
                    )
                    self._log_failure(article, error)
                    logger.exception(f"Error processing article {article.pocket_id}")
                    continue

        finally:
            # Generate and log the final report
            logger.info("\nProcessing Complete")
            logger.info("=" * 50)
            logger.info(self._generate_failure_report())

            # Log any remaining articles that weren't processed
            remaining = total_articles - self.stats["total_processed"]
            if remaining > 0:
                logger.warning(f"{remaining} articles were not processed due to " "rate limits or early termination")

    def get_processing_stats(self) -> Dict[str, int]:
        """
        Get current processing statistics.

        Returns:
            Dict[str, int]: Dictionary containing current processing statistics
        """
        return self.stats.copy()
