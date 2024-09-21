import argparse

from loguru import logger

import database
import utils
from content_fetcher.fetcher import ContentFetcher
from models import Article
from openai_processor.processor import OpenAIProcessor
from pocket_api.pocket_client import PocketClient


def main():
    utils.setup_logging()
    parser = argparse.ArgumentParser(description="Pocket GPT CLI Tool")
    parser.add_argument("--fetch-pocket", action="store_true", help="Fetch articles from Pocket")
    parser.add_argument("--fetch-content", action="store_true", help="Fetch content for articles")
    parser.add_argument("--process-articles", action="store_true", help="Process articles with OpenAI GPT")
    parser.add_argument("--update-tags", action="store_true", help="Update articles in Pocket with tags")
    args = parser.parse_args()

    session = database.get_session()
    pocket_client = PocketClient(session)
    content_fetcher = ContentFetcher()
    openai_processor = OpenAIProcessor()

    if args.fetch_pocket:
        pocket_client.fetch_articles()

    if args.fetch_content:
        fetch_content_for_articles(session, content_fetcher)

    if args.process_articles:
        process_articles_with_gpt(session, openai_processor)

    if args.update_tags:
        update_pocket_tags(session, pocket_client)


def fetch_content_for_articles(session, content_fetcher):
    logger.info("Fetching content for articles")
    articles = session.query(Article).filter(Article.content.is_(None)).all()
    for article in articles:
        content = content_fetcher.fetch_content(article.url)
        if content:
            article.content = content
            session.commit()
            logger.info(f"Content fetched for article {article.pocket_id}")
        else:
            logger.warning(f"No content fetched for article {article.pocket_id}")


def process_articles_with_gpt(session, openai_processor):
    logger.info("Processing articles with OpenAI GPT")
    articles = session.query(Article).filter(Article.content.isnot(None), Article.summary.is_(None)).all()
    for article in articles:
        if not article.content:
            logger.warning(f"No content for article {article.pocket_id}, skipping.")
            continue
        summary = openai_processor.generate_summary(article.content)
        tags = openai_processor.generate_tags(article.content)
        article.summary = summary
        article.tags = ",".join(tags)
        session.commit()
        logger.info(f"Article {article.pocket_id} processed")


def update_pocket_tags(session, pocket_client):
    logger.info("Updating Pocket articles with new tags")
    articles = session.query(Article).filter(Article.tags.isnot(None)).all()
    for article in articles:
        tags = article.tags.split(",")
        success = pocket_client.add_tags_to_article(article.pocket_id, tags)
        if success:
            logger.info(f"Tags updated for article {article.pocket_id}")
        else:
            logger.error(f"Failed to update tags for article {article.pocket_id}")


if __name__ == "__main__":
    main()
