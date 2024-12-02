import argparse
import json

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
from pocket_api.auth import PocketAuth
from pocket_api.pocket_client import PocketClient


def setup_parser():
    """Set up command-line argument parser."""
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
    actions_group.add_argument(
        "--load-missing",
        action="store_true",
        help="Load missing articles from Pocket into the local database",
    )
    actions_group.add_argument(
        "--delete-all",
        action="store_true",
        help="Delete all articles from the local database and Pocket account",
    )

    info_group.add_argument("--list-incomplete", action="store_true", help="List articles without title or URL")
    info_group.add_argument("--list-articles", action="store_true", help="List all fetched articles")
    info_group.add_argument("--db-info", action="store_true", help="Display database statistics")
    info_group.add_argument("--check-auth-status", action="store_true", help="Check Pocket API authentication status")
    info_group.add_argument(
        "--list-missing",
        action="store_true",
        help="List articles in Pocket that are not in the local database",
    )

    parser.add_argument("--get-article-by-url", type=str, help="Get article information by its original URL")
    parser.add_argument("--authenticate", action="store_true", help="Authenticate with the Pocket API")

    return parser


def authenticate_user(pocket_auth):
    """Authenticate user and update environment file."""
    try:
        new_access_token = pocket_auth.authenticate()
        if new_access_token:
            from dotenv import find_dotenv, set_key

            dotenv_path = find_dotenv()
            if dotenv_path:
                set_key(dotenv_path, "POCKET_ACCESS_TOKEN", new_access_token)
                logger.info("Access token updated in .env file.")
            else:
                logger.error(".env file not found.")
        else:
            logger.error("Authentication failed.")
    except Exception as e:
        logger.error(f"Authentication process failed: {e}")


def execute_actions(args, session, pocket_client, pocket_auth, content_fetcher, openai_processor):
    """Execute actions based on the parsed arguments."""
    if args.authenticate:
        authenticate_user(pocket_auth)

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

    if args.check_auth_status:
        auth_status = pocket_auth.check_authentication_status()
        logger.info(f"Authentication Status: {auth_status}")

    if args.list_missing:
        missing_articles = pocket_client.get_articles_not_in_db()
        for pocket_id in missing_articles:
            logger.info(f"Missing Article ID: {pocket_id}")

    if args.load_missing:
        pocket_client.load_missing_articles(batch_size=5)

    if args.get_article_by_url:
        article_data = pocket_client.get_article_by_url(args.get_article_by_url)
        if article_data:
            logger.info("Article Data:\n" + json.dumps(article_data, indent=4, ensure_ascii=False))
        else:
            logger.info("No article found for the provided URL.")

    if args.delete_all:
        auth_status = pocket_auth.check_authentication_status()
        if auth_status["status"] == "success":
            pocket_client.delete_all_articles()
        else:
            logger.error("Authentication failed. Cannot proceed with deleting articles.")


def main():
    parser = setup_parser()
    args = parser.parse_args()

    session = get_session()
    pocket_client = PocketClient(session)
    pocket_auth = PocketAuth()
    content_fetcher = ContentFetcher(session)
    openai_processor = OpenAIProcessor()

    try:
        execute_actions(args, session, pocket_client, pocket_auth, content_fetcher, openai_processor)
    finally:
        session.close()


if __name__ == "__main__":
    main()
