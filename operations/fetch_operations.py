import time

from loguru import logger
from sqlalchemy import or_

from content_fetcher.fetcher import ContentFetcher
from models import Article


def fetch_content_for_articles(session, content_fetcher: ContentFetcher):
    logger.info("Starting content fetch for articles")
    articles = (
        session.query(Article)
        .filter(
            (Article.content.is_(None) | (Article.content == ""))
            & (Article.content_html.is_(None) | (Article.content_html == ""))
            & (Article.firecrawl_metadata.is_(None))
        )
        .all()
    )
    logger.info(f"Found {len(articles)} articles needing content")
    for idx, article in enumerate(articles, 1):
        logger.info(f"Processing article {idx}/{len(articles)} (ID: {article.pocket_id})")
        try:
            success = content_fetcher.fetch_and_save_content(article)
            if success:
                logger.info(f"Successfully fetched content for article {article.pocket_id}")
            else:
                logger.warning(f"Failed to fetch content for article {article.pocket_id}")
        except Exception as e:
            logger.error(f"Error processing article {article.pocket_id}: {str(e)}")
        time.sleep(1)
    logger.info("Content fetch completed")


def list_incomplete_articles(session):
    incomplete_articles = (
        session.query(Article)
        .filter(
            or_(
                Article.title.is_(None),
                Article.title == "",
                Article.url.is_(None),
                Article.url == "",
            )
        )
        .all()
    )
    logger.info(f"Found {len(incomplete_articles)} incomplete articles")
    return incomplete_articles


def list_all_articles(session):
    articles = session.query(Article).order_by(Article.date_added.desc()).all()
    logger.info(f"Found {len(articles)} articles")
    return articles
