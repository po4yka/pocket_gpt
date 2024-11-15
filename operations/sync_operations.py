from loguru import logger

from models import Article
from pocket_api.pocket_client import PocketClient


def update_pocket_tags(session, pocket_client: PocketClient):
    logger.info("Updating Pocket articles with new tags")
    articles = session.query(Article).filter(Article.tags.isnot(None)).all()
    for article in articles:
        tags = article.tags.split(",")
        success = pocket_client.add_tags_to_article(article.pocket_id, tags)
        if success:
            logger.info(f"Tags updated for article {article.pocket_id}")
        else:
            logger.error(f"Failed to update tags for article {article.pocket_id}")


def check_pocket_sync_status(session, pocket_client: PocketClient):
    logger.info("Checking Pocket sync status")
    status = pocket_client.get_sync_status()
    logger.info(f"Sync status: {status}")
