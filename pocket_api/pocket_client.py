import json

import requests
from loguru import logger

from config import POCKET_ACCESS_TOKEN, POCKET_CONSUMER_KEY
from models import Article


class PocketClient:
    def __init__(self, session):
        self.session = session
        self.consumer_key = POCKET_CONSUMER_KEY
        self.access_token = POCKET_ACCESS_TOKEN
        self.base_url = "https://getpocket.com/v3"

    def fetch_articles(self):
        logger.info("Fetching articles from Pocket")
        url = f"{self.base_url}/get"
        params = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "state": "all",
            "detailType": "complete",
        }
        response = requests.post(url, json=params)
        if response.status_code != 200:
            logger.error(f"Failed to fetch articles: {response.text}")
            return
        articles = response.json().get("list", {})
        for pocket_id, item in articles.items():
            if self.session.query(Article).filter_by(pocket_id=pocket_id).first():
                logger.info(f"Article {pocket_id} already exists, skipping.")
                continue
            article = Article(
                pocket_id=pocket_id,
                title=item.get("resolved_title") or item.get("given_title"),
                url=item.get("resolved_url") or item.get("given_url"),
                pocket_data=json.dumps(item),
            )
            self.session.add(article)
            self.session.commit()
            logger.info(f"Article {pocket_id} saved to database.")

    def add_tags_to_article(self, pocket_item_id, tags):
        logger.info(f"Adding tags to Pocket article {pocket_item_id}: {tags}")
        url = f"{self.base_url}/send"
        actions = [{"action": "tags_add", "item_id": pocket_item_id, "tags": ",".join(tags)}]
        params = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "actions": actions,
        }
        response = requests.post(url, json=params)
        if response.status_code != 200:
            logger.error(f"Failed to add tags: {response.text}")
            return False
        return True
