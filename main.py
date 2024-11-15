import argparse

from loguru import logger

from content_fetcher.fetcher import ContentFetcher
from database import get_session
from openai_processor.processor import OpenAIProcessor
from operations.fetch_operations import (
    fetch_content_for_articles,
    list_all_articles,
    list_incomplete_articles,
)
from operations.process_operations import process_articles_with_gpt
from operations.sync_operations import update_pocket_tags
from operations.utils import get_database_info
from pocket_api.pocket_client import PocketClient


def main():
    parser = argparse.ArgumentParser(
        description="Pocket GPT CLI Tool",
        epilog="For more details, refer to the README or contact support.",
    )

    actions_group = parser.add_argument_group("Actions", "Choose one or more actions to perform")
    info_group = parser.add_argument_group("Info", "Inspect database or articles")

    actions_group.add_argument("--fetch-content", action="store_true", help="Fetch content for articles missing data")
    actions_group.add_argument(
        "--process-articles",
        action="store_true",
        help="Process articles using OpenAI GPT for summaries and tags",
    )
    actions_group.add_argument(
        "--update-tags",
        action="store_true",
        help="Update Pocket articles with newly generated tags",
    )

    info_group.add_argument("--list-incomplete", action="store_true", help="List articles without title or URL")
    info_group.add_argument("--list-articles", action="store_true", help="List all fetched articles")
    info_group.add_argument("--db-info", action="store_true", help="Display database statistics")

    args = parser.parse_args()

    session = get_session()
    pocket_client = PocketClient(session)
    content_fetcher = ContentFetcher(session)
    openai_processor = OpenAIProcessor()

    try:
        if args.fetch_content:
            fetch_content_for_articles(session, content_fetcher)
        if args.process_articles:
            process_articles_with_gpt(session, openai_processor)
        if args.update_tags:
            update_pocket_tags(session, pocket_client)
        if args.list_incomplete:
            incomplete_articles = list_incomplete_articles(session)
            for article in incomplete_articles:
                logger.info(f"Incomplete Article: {article}")
        if args.list_articles:
            articles = list_all_articles(session)
            for article in articles:
                logger.info(f"Article: {article}")
        if args.db_info:
            db_info = get_database_info(session)
            logger.info(f"Database Info: {db_info}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
