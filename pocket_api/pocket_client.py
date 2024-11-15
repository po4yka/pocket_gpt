from time import sleep
from typing import Any, Dict, List, Optional, cast

import requests
from loguru import logger
from requests.structures import CaseInsensitiveDict
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from config import POCKET_ACCESS_TOKEN, POCKET_CONSUMER_KEY
from database import get_session
from models import Article

POCKET_GET_URL = "https://getpocket.com/v3/get"


class PocketClient:
    def __init__(self, session=get_session()) -> None:
        self.consumer_key = POCKET_CONSUMER_KEY
        self.access_token = POCKET_ACCESS_TOKEN
        self.session = session

    def _check_rate_limit(self, headers: CaseInsensitiveDict[str]) -> None:
        """Check and respect rate limits based on response headers."""
        user_remaining = int(headers.get("X-Limit-User-Remaining", "1"))
        user_reset = int(headers.get("X-Limit-User-Reset", "0"))
        key_remaining = int(headers.get("X-Limit-Key-Remaining", "1"))
        key_reset = int(headers.get("X-Limit-Key-Reset", "0"))

        if user_remaining == 0:
            logger.warning(f"User limit reached. Waiting {user_reset} seconds.")
            sleep(user_reset)

        if key_remaining == 0:
            logger.warning(f"Consumer key limit reached. Waiting {key_reset} seconds.")
            sleep(key_reset)

    def _fetch_page(self, count: int, offset: int) -> Optional[Dict[str, Any]]:
        """Fetch a single page of articles with pagination."""
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "count": count,
            "offset": offset,
            "detailType": "complete",
        }

        logger.info(f"Fetching articles: offset={offset}, count={count}...")
        response = requests.post(POCKET_GET_URL, json=payload)

        if response.status_code != 200:
            logger.error(f"Failed to fetch articles: {response.text}")
            return None

        self._check_rate_limit(cast(CaseInsensitiveDict[str], response.headers))

        data = response.json()
        return data

    def fetch_all_articles(self) -> None:
        """Fetch all articles incrementally with rate limit handling."""
        offset = 0
        count = 30  # Max allowed per request
        more_articles = True

        # Initial call to get the total number of articles
        data = self._fetch_page(1, 0)  # Fetch just one article to get 'total'
        if not data or "list" not in data:
            logger.info("No articles to fetch.")
            return

        total = int(data.get("total", 0))
        logger.info(f"Total articles to download: {total}")

        # Use tqdm to display a progress bar
        with tqdm(total=total, desc="Downloading Articles", unit="article") as pbar:
            while more_articles:
                data = self._fetch_page(count, offset)
                if not data or "list" not in data:
                    logger.info("No more articles to fetch.")
                    break

                articles = data["list"]
                self._save_articles_to_db(articles)

                fetched_count = len(articles)
                offset += fetched_count
                pbar.update(fetched_count)

                if fetched_count < count:
                    more_articles = False  # No more pages left to fetch

    def _save_articles_to_db(self, articles: Dict[str, Any]) -> None:
        """
        Save articles from the response to the local database, handling duplicates gracefully.

        Args:
            articles (Dict[str, Any]): Articles from Pocket API response.
        """
        for item_id, article_data in articles.items():
            # Check if the article already exists in the database
            existing_article = self.session.query(Article).filter_by(pocket_id=item_id).first()
            if existing_article:
                logger.info(f"Article {item_id} already exists in the database. Skipping.")
                continue

            # Create a new Article object and save it
            try:
                article = Article(
                    pocket_id=item_id,
                    title=article_data.get("resolved_title"),
                    url=article_data.get("resolved_url"),
                    content=article_data.get("excerpt"),
                    tags=",".join(article_data.get("tags", {}).keys()),
                    pocket_data=str(article_data),
                )
                self.session.add(article)
            except Exception as e:
                logger.error(f"Error creating article {item_id}: {e}")

        try:
            self.session.commit()
            logger.info("Articles saved to the database.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error committing articles to the database: {e}")

    def sync_articles(self, since: Optional[int] = None) -> None:
        """Sync only new or updated articles since the last retrieval."""
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "detailType": "complete",
        }
        if since:
            payload["since"] = str(since)

        logger.info(f"Syncing articles since {since}...")
        response = requests.post(POCKET_GET_URL, json=payload)

        if response.status_code != 200:
            logger.error(f"Failed to sync articles: {response.text}")
            return

        self._check_rate_limit(cast(CaseInsensitiveDict[str], response.headers))

        data = response.json()
        if "list" in data:
            self._save_articles_to_db(data["list"])

        logger.info("Sync completed.")

    def get_sync_status(self) -> Dict[str, Any]:
        """Get sync status between Pocket service and local database."""
        # First check if we have valid credentials
        if not self.consumer_key or not self.access_token:
            logger.error("Missing Pocket API credentials")
            return {"error": "Missing credentials"}

        # Get total count from Pocket
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "state": "all",  # Get both unread and archived items
            "count": 1,  # Only need one item to get total
            "detailType": "simple",  # Minimize data transfer
            "total": 1,  # Request total count in response
        }

        try:
            logger.info("Fetching Pocket article count...")
            response = requests.post(
                POCKET_GET_URL,
                json=payload,
                headers={"Content-Type": "application/json", "X-Accept": "application/json"},
            )

            if response.status_code == 401:
                logger.error("Invalid or expired access token")
                return {"error": "Authentication failed"}

            if response.status_code != 200:
                logger.error(f"Failed to fetch articles: {response.text}")
                return {"error": f"API error: {response.text}"}

            self._check_rate_limit(cast(CaseInsensitiveDict[str], response.headers))

            data = response.json()
            if "status" not in data or data["status"] != 1:
                logger.error(f"Invalid response from Pocket API: {data}")
                return {"error": "Invalid API response"}

            total_pocket_count = int(data.get("total", 0))

            # Get local count from database
            local_count = self.session.query(Article).count()

            return {
                "pocket_count": total_pocket_count,
                "local_count": local_count,
                "is_synced": total_pocket_count == local_count,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Error checking sync status: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}"}

    def add_tags_to_article(self, pocket_id: str, tags: list[str]) -> bool:
        """Add tags to a specific article in Pocket."""
        url = "https://getpocket.com/v3/send"
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "actions": [{"action": "tags_add", "item_id": pocket_id, "tags": ",".join(tags)}],
        }

        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Successfully added tags to article {pocket_id}")
                return True
            else:
                logger.error(f"Failed to add tags to article {pocket_id}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error adding tags to article {pocket_id}: {e}")
            return False

    def get_articles_not_in_db(self) -> List[str]:
        """
        Check for articles in Pocket that are not in the local database.
        Returns a list of Pocket IDs for these articles.
        """
        # Fetch all articles from Pocket
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "state": "all",  # Get all articles (unread and archived)
            "detailType": "simple",  # Only basic details to minimize data transfer
        }

        logger.info("Fetching articles from Pocket...")
        response = requests.post(
            POCKET_GET_URL,
            json=payload,
            headers={"Content-Type": "application/json", "X-Accept": "application/json"},
        )

        if response.status_code != 200:
            logger.error(f"Failed to fetch articles from Pocket: {response.text}")
            return []

        pocket_articles = response.json().get("list", {})
        pocket_ids = set(pocket_articles.keys())

        # Fetch all Pocket IDs from the database
        db_pocket_ids = {row[0] for row in self.session.query(Article.pocket_id).all()}

        # Find IDs that are in Pocket but not in the database
        missing_ids = pocket_ids - db_pocket_ids
        logger.info(f"Found {len(missing_ids)} articles in Pocket that are not in the database.")

        return list(missing_ids)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=1, max=10))
    def fetch_batch(self, payload: dict) -> dict:
        """
        Fetch a batch of articles with retry on failure.

        Args:
            payload (dict): The payload to send to the Pocket API.

        Returns:
            dict: The response JSON from the Pocket API.

        Raises:
            Exception: If the request fails after retries.
        """
        response = requests.post(
            POCKET_GET_URL,
            json=payload,
            headers={"Content-Type": "application/json", "X-Accept": "application/json"},
        )
        if response.status_code != 200:
            raise Exception(f"Pocket API error: {response.text}")
        return response.json()

    def load_missing_articles(self, batch_size: int = 10) -> None:
        """
        Load only missing articles from Pocket into the local database in batches.

        Args:
            batch_size (int): Number of articles to fetch per batch.
        """
        # Get IDs of articles missing in the local database
        missing_ids = self.get_articles_not_in_db()
        if not missing_ids:
            logger.info("No missing articles to load.")
            return

        logger.info(f"Total missing articles: {len(missing_ids)}. Fetching in batches of {batch_size}...")
        for i in range(0, len(missing_ids), batch_size):
            batch_ids = list(missing_ids)[i : i + batch_size]

            # Prepare the payload for this batch
            payload = {
                "consumer_key": self.consumer_key,
                "access_token": self.access_token,
                "detailType": "complete",
                "item_ids": ",".join(batch_ids),  # Fetch only the specific IDs
            }

            logger.info(f"Fetching batch {i // batch_size + 1}: {batch_ids}")
            try:
                # Fetch the batch
                response = self.fetch_batch(payload)  # Use retry-enabled fetch
                pocket_articles = response.get("list", {})

                # Save fetched articles to the database
                self._save_articles_to_db(pocket_articles)
                logger.info(f"Batch {i // batch_size + 1} loaded successfully.")
            except Exception as e:
                logger.error(f"Error fetching batch {i // batch_size + 1}: {str(e)}")

    def get_article_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve article information by its original URL.

        Args:
            url (str): The original URL of the article to retrieve.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the article information if found, None otherwise.
        """
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "search": url,
            "detailType": "complete",
        }

        logger.info(f"Fetching article by URL: {url}")

        try:
            response = requests.post(POCKET_GET_URL, json=payload)

            if response.status_code != 200:
                logger.error(f"Failed to fetch article by URL. Response: {response.text}")
                return None

            data = response.json()
            articles = data.get("list", {})

            if not articles:
                logger.warning(f"No article found for URL: {url}")
                return None

            # Pocket API can return multiple matches; we take the first one
            first_article = next(iter(articles.values()), None)
            if first_article:
                logger.info(f"Article found for URL: {url}")
                return first_article
            else:
                logger.warning(f"No valid article data for URL: {url}")
                return None
        except Exception as e:
            logger.error(f"Error retrieving article by URL: {e}")
            return None

    def delete_all_articles(self, batch_size=25) -> None:
        """
        Delete all articles from the local database and the user's Pocket account in batches.

        Handles timeouts and retries using batch processing and exponential backoff.
        """
        logger.info("Starting deletion of all articles from the local database and Pocket account.")

        # Fetch all articles from the local database
        articles = self.session.query(Article).all()
        if not articles:
            logger.info("No articles found in the local database. Nothing to delete.")
            return

        logger.info(f"Found {len(articles)} articles in the local database.")

        # Prepare articles for batch processing
        actions = [{"action": "delete", "item_id": article.pocket_id} for article in articles]

        # Process in batches
        for batch_start in range(0, len(actions), batch_size):
            batch_actions = actions[batch_start : batch_start + batch_size]
            logger.info(f"Processing batch {batch_start // batch_size + 1} with {len(batch_actions)} articles.")

            try:
                self._delete_articles_batch(batch_actions)
            except Exception as e:
                logger.error(f"Failed to delete batch starting at index {batch_start}: {e}")

        # Delete all articles from the local database
        try:
            logger.info("Deleting all articles from the local database.")
            self.session.query(Article).delete()
            self.session.commit()
            logger.info("All articles successfully deleted from the local database.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error deleting articles from the local database: {e}")
            raise

        logger.info("Completed deletion of all articles.")

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    def _delete_articles_batch(self, batch_actions):
        """
        Delete a batch of articles using Pocket's API with retry logic.
        """
        pocket_delete_url = "https://getpocket.com/v3/send"
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "actions": batch_actions,
        }

        logger.info("Sending batch delete request to Pocket API.")
        response = requests.post(pocket_delete_url, json=payload)

        # Log raw response details for debugging
        logger.debug(f"Response Status Code: {response.status_code}")
        logger.debug(f"Response Content: {response.text[:500]}")  # Log the first 500 characters

        if response.headers.get("Content-Type", "").startswith("text/html"):
            logger.error("Received an HTML response instead of JSON.")
            raise Exception("Unexpected HTML response from Pocket API.")

        if response.status_code != 200:
            logger.error(f"Pocket API returned an error. Status Code: {response.status_code}")
            response.raise_for_status()

        try:
            response_data = response.json()
        except ValueError as e:
            logger.error(f"Error decoding JSON response: {e}")
            logger.error(f"Response Content: {response.text}")
            raise Exception("Invalid response from Pocket API. Expected JSON format.") from e

        # Log action results
        if response_data.get("status") == 1:
            logger.info("Batch delete request completed successfully on Pocket API.")
            action_results = response_data.get("action_results", [])
            success_count = action_results.count(True)
            failure_count = len(action_results) - success_count
            logger.info(f"Pocket API results: Success={success_count}, Failures={failure_count}")

            # Log detailed action errors
            if "action_errors" in response_data:
                for i, error in enumerate(response_data["action_errors"]):
                    logger.error(f"Action {i} Error: {error}")

        else:
            logger.error(f"Pocket API reported failure: {response_data}")
            raise Exception(f"Pocket API error: {response_data.get('error', 'Unknown error')}")
