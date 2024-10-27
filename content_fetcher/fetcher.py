import json
import time
from datetime import datetime
from typing import Optional, Tuple

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

    def __init__(
        self,
        session: Session,
        max_retries: int = 3,
        min_wait_time: float = 3.0,  # Set to ensure we stay under 20 requests/minute
        requests_per_minute: int = 20,
        total_requests_limit: int = 3000,
    ):
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

        logger.info(
            f"ContentFetcher initialized with rate limits: "
            f"{requests_per_minute} requests/minute, "
            f"{total_requests_limit} total requests"
        )

    def _wait_for_rate_limit(self):
        """
        Wait if necessary to comply with rate limits.
        """
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
        """
        Update the rate limit counters after a successful request.
        """
        self.request_count += 1
        self.minute_request_count += 1
        self.last_request_time = time.time()

    def _parse_rate_limit_response(self, response_text: str) -> Tuple[float, datetime]:
        """
        Parse rate limit information from the API response.

        Args:
            response_text (str): The response text from the API.

        Returns:
            Tuple[float, datetime]: The wait time in seconds and reset time.
        """
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
        """
        Handle rate limit response and determine wait time.

        Args:
            response (requests.Response): The API response.
            retry_count (int): Current retry attempt number.

        Returns:
            Optional[float]: Wait time in seconds, or None if max retries exceeded.
        """
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

    def fetch_and_save_content(self, article: Article) -> bool:
        """
        Fetch content for a single article and save it to the database.

        Args:
            article (Article): The Article object to fetch content for.

        Returns:
            bool: True if content was successfully fetched and saved, False otherwise.
        """
        if not article.url:
            logger.warning(f"No URL provided for article: {article.pocket_id}")
            return False

        retry_count = 0
        while retry_count <= self.max_retries:
            try:
                # Wait for rate limit if necessary
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
                    logger.error(f"Rate limit error response: {response.text}")
                    wait_time = self._handle_rate_limit(response, retry_count)

                    if wait_time is None:
                        return False

                    time.sleep(wait_time)
                    retry_count += 1
                    continue

                response.raise_for_status()

                # Update rate limit counters after successful request
                self._update_rate_limit_counters()

                result = response.json()
                if not result.get("success"):
                    logger.error(f"API returned unsuccessful response for article {article.pocket_id}")
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
                        f"Content and metadata saved for article: {article.pocket_id}. "
                        f"Total requests: {self.request_count}/{self.total_requests_limit}, "
                        f"Minute requests: {self.minute_request_count}/{self.requests_per_minute}"
                    )
                    return True
                else:
                    logger.warning(f"No content data received for article: {article.pocket_id}")
                    return False

            except requests.RequestException as e:
                logger.error(f"API request error for article {article.pocket_id}: {e}")
                if e.response is not None:
                    logger.error(f"Response content: {e.response.text}")

                    if e.response.status_code == 429:  # Too Many Requests
                        wait_time = self._handle_rate_limit(e.response, retry_count)
                        if wait_time is None:
                            return False
                        time.sleep(wait_time)
                        retry_count += 1
                        continue

                return False
            except Exception as e:
                logger.error(f"Unexpected error processing article {article.pocket_id}: {e}")
                return False

        return False

    def fetch_content_for_all_articles(self) -> None:
        """
        Fetch content for all articles in the database that don't have content yet.
        """
        logger.info("Starting content fetch for all articles without content")

        # Check if we have enough requests available
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

        for index, article in enumerate(articles, 1):
            if self.request_count >= self.total_requests_limit:
                logger.warning("Total request limit reached. Stopping processing.")
                break

            logger.info(
                f"Processing article {index}/{total_articles}: {article.pocket_id} "
                f"(Total requests: {self.request_count}/{self.total_requests_limit})"
            )

            if not article.url:
                logger.warning(f"Skipping article {article.pocket_id} - No URL available")
                continue

            success = self.fetch_and_save_content(article)
            if success:
                logger.info(f"Successfully fetched content for article: {article.pocket_id}")
            else:
                logger.warning(f"Failed to fetch content for article: {article.pocket_id}")

        logger.info(
            f"Completed content fetch. Total requests made: {self.request_count}, "
            f"Articles processed: {index}/{total_articles}"
        )
