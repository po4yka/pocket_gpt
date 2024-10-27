import argparse

from loguru import logger
from sqlalchemy import func, or_

import database
import utils
from content_fetcher.fetcher import ContentFetcher
from models import Article
from openai_processor.processor import OpenAIProcessor
from pocket_api.auth import PocketAuth
from pocket_api.pocket_client import PocketClient


def main():
    utils.setup_logging()

    parser = argparse.ArgumentParser(description="Pocket GPT CLI Tool")
    parser.add_argument("--fetch-pocket", action="store_true", help="Fetch articles from Pocket")
    parser.add_argument("--fetch-content", action="store_true", help="Fetch content for articles")
    parser.add_argument("--process-articles", action="store_true", help="Process articles with OpenAI GPT")
    parser.add_argument("--update-tags", action="store_true", help="Update articles in Pocket with tags")
    parser.add_argument("--authenticate", action="store_true", help="Authenticate with Pocket and get access token")
    parser.add_argument("--list-incomplete", action="store_true", help="List articles without title and description")
    parser.add_argument("--list-articles", action="store_true", help="List all fetched articles")
    parser.add_argument("--db-info", action="store_true", help="Get database information")
    args = parser.parse_args()

    if args.authenticate:
        auth = PocketAuth()
        access_token = auth.authenticate()
        print(f"Access token: {access_token}")
        return

    session = database.get_session()
    pocket_client = PocketClient(session)
    content_fetcher = ContentFetcher(session)
    openai_processor = OpenAIProcessor()

    if args.fetch_pocket:
        pocket_client.fetch_all_articles()

    if args.fetch_content:
        fetch_content_for_articles(session, content_fetcher)

    if args.process_articles:
        process_articles_with_gpt(session, openai_processor)

    if args.update_tags:
        update_pocket_tags(session, pocket_client)

    if args.list_incomplete:
        list_incomplete_articles(session)

    if args.list_articles:
        list_all_articles(session)

    if args.db_info:
        get_database_info(session)


def fetch_content_for_articles(session, content_fetcher):
    logger.info("Fetching content for articles")
    articles = (
        session.query(Article)
        .filter(
            (Article.content.is_(None) | (Article.content == ""))
            & (Article.content_html.is_(None) | (Article.content_html == ""))
            & (Article.firecrawl_metadata.is_(None))
        )
        .all()
    )
    for article in articles:
        success = content_fetcher.fetch_and_save_content(article)
        if success:
            logger.info(f"Content fetched for article {article.pocket_id}")
        else:
            logger.warning(f"Failed to fetch content for article {article.pocket_id}")


def process_articles_with_gpt(session, openai_processor):
    logger.info("Processing articles with OpenAI GPT")
    articles = session.query(Article).filter(Article.content.isnot(None), Article.summary_20.is_(None)).all()
    for article in articles:
        if not article.content:
            logger.warning(f"No content for article {article.pocket_id}, skipping.")
            continue

        try:
            summaries = openai_processor.generate_summaries(article.content)
            summary_20 = summaries["20_words"]
            summary_50 = summaries["50_words"]
            summary_100 = summaries["100_words"]
            unlimited_summary = summaries["unlimited"]

            tags = openai_processor.generate_tags(article.content)

            article.summary_20 = summary_20
            article.summary_50 = summary_50
            article.summary_100 = summary_100
            article.unlimited_summary = unlimited_summary
            article.tags = ",".join(tags)
            session.commit()

            logger.info(f"Article {article.pocket_id} processed successfully.")
        except Exception as e:
            logger.error(f"Error processing article {article.pocket_id}: {e}")


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


def list_incomplete_articles(session):
    logger.info("Listing articles without title and URL")
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

    if not incomplete_articles:
        logger.info("No incomplete articles found.")
    else:
        logger.info(f"Found {len(incomplete_articles)} incomplete articles:")
        for article in incomplete_articles:
            pocket_link = f"https://getpocket.com/read/{article.pocket_id}"
            logger.info(f"Article ID: {article.pocket_id}")
            logger.info(f"Pocket Link: {pocket_link}")

            if not article.url:
                article.url = pocket_link
                session.commit()
                logger.info(f"Updated URL: {article.url}")

            logger.info("---")


def list_all_articles(session):
    logger.info("Listing all fetched articles")
    articles = session.query(Article).order_by(Article.date_added.desc()).all()

    if not articles:
        logger.info("No articles found.")
    else:
        logger.info(f"Found {len(articles)} articles:")
        for article in articles:
            logger.info(f"Article ID: {article.pocket_id}")
            logger.info(f"Title: {article.title}")
            logger.info(f"URL: {article.url}")
            logger.info(f"Date Added: {article.date_added}")
            logger.info("---")


def get_database_info(session):
    logger.info("Fetching database information")

    total_articles = session.query(func.count(Article.id)).scalar()
    articles_with_content = session.query(func.count(Article.id)).filter(Article.content.isnot(None)).scalar()
    articles_with_summary = session.query(func.count(Article.id)).filter(Article.summary_20.isnot(None)).scalar()
    articles_with_tags = session.query(func.count(Article.id)).filter(Article.tags.isnot(None)).scalar()

    logger.info(f"Total articles: {total_articles}")
    logger.info(f"Articles with content: {articles_with_content}")
    logger.info(f"Articles with summary: {articles_with_summary}")
    logger.info(f"Articles with tags: {articles_with_tags}")


if __name__ == "__main__":
    main()
