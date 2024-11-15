from time import sleep
from typing import Any, Dict, Optional, cast

import requests
from loguru import logger
from requests.structures import CaseInsensitiveDict
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
        """Save articles from the response to the local database."""
        for item_id, article_data in articles.items():
            article = Article(
                pocket_id=item_id,
                title=article_data.get("resolved_title"),
                url=article_data.get("resolved_url"),
                content=article_data.get("excerpt"),
                tags=",".join(article_data.get("tags", {}).keys()),
                pocket_data=str(article_data),
            )
            self.session.merge(article)  # Avoid duplicates
        self.session.commit()
        logger.info("Articles saved to the database.")

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

    def delete_article(self, pocket_id: str) -> bool:
        """Delete an article from Pocket."""
        url = "https://getpocket.com/v3/send"
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "actions": [{"action": "delete", "item_id": pocket_id}],
        }

        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Successfully deleted article {pocket_id} from Pocket")
                return True
            else:
                logger.error(f"Failed to delete article {pocket_id}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error deleting article {pocket_id}: {e}")
            return False

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
