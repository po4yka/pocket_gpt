from typing import Any, Dict, List, Optional, cast

import requests
from loguru import logger
from requests.structures import CaseInsensitiveDict
from sqlalchemy.orm import Session
from tqdm import tqdm

from config import POCKET_ACCESS_TOKEN, POCKET_CONSUMER_KEY
from models import Article

POCKET_GET_URL = "https://getpocket.com/v3/get"
POCKET_SEND_URL = "https://getpocket.com/v3/send"


class PocketClient:
    def __init__(self, session: Session):
        self.consumer_key = POCKET_CONSUMER_KEY
        self.access_token = POCKET_ACCESS_TOKEN
        self.session = session

    def _post_request(self, url: str, payload: dict) -> Optional[dict]:
        headers = {"Content-Type": "application/json", "X-Accept": "application/json"}
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(f"Error from Pocket API ({url}): {response.text}")
            return None
        return response.json()

    def fetch_all_articles(self, count=30):
        offset = 0
        total = self._get_total_count()
        with tqdm(total=total, desc="Fetching articles") as pbar:
            while offset < total:
                data = self._fetch_page(count, offset)
                if data and "list" in data:
                    self._save_articles_to_db(data["list"])
                    offset += len(data["list"])
                    pbar.update(len(data["list"]))
                else:
                    break

    def add_tags_to_article(self, pocket_id: str, tags: List[str]) -> bool:
        """Add tags to a specific article in Pocket."""
        url = "https://getpocket.com/v3/send"
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "actions": [{"action": "tags_add", "item_id": pocket_id, "tags": ",".join(tags)}],
        }

        try:
            response = requests.post(url, json=payload)
            self._check_rate_limit(cast(CaseInsensitiveDict[str], response.headers))

            if response.status_code == 200:
                logger.info(f"Successfully added tags to article {pocket_id}")
                return True
            else:
                logger.error(f"Failed to add tags to article {pocket_id}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error adding tags to article {pocket_id}: {e}")
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

    def _fetch_page(self, count: int, offset: int) -> Optional[dict]:
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "count": count,
            "offset": offset,
            "detailType": "complete",
        }
        return self._post_request(POCKET_GET_URL, payload)

    def _get_total_count(self) -> int:
        response = self._fetch_page(1, 0)
        return int(response.get("total", 0)) if response else 0

    def _save_articles_to_db(self, articles: Dict[str, Any]):
        for item_id, article_data in articles.items():
            if self.session.query(Article).filter_by(pocket_id=item_id).first():
                logger.info(f"Article {item_id} already exists. Skipping.")
                continue
            self.session.add(
                Article(
                    pocket_id=item_id,
                    title=article_data.get("resolved_title"),
                    url=article_data.get("resolved_url"),
                    content=article_data.get("excerpt"),
                    tags=",".join(article_data.get("tags", {}).keys()),
                )
            )
        self.session.commit()

    def _check_rate_limit(self, headers: CaseInsensitiveDict[str]) -> None:
        """Check rate limit headers and log if limits are close."""
        remaining = headers.get("X-Limit-User-Remaining")
        if remaining and int(remaining) < 10:
            logger.warning(f"Approaching Pocket API rate limit. Remaining: {remaining}")
