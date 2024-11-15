from loguru import logger

from models import Article
from openai_processor.processor import OpenAIProcessor


def process_articles_with_gpt(session, openai_processor: OpenAIProcessor):
    logger.info("Processing articles with OpenAI GPT")
    articles = session.query(Article).filter(Article.content.isnot(None), Article.summary_20.is_(None)).all()
    for article in articles:
        if not article.content:
            logger.warning(f"No content for article {article.pocket_id}, skipping.")
            continue
        try:
            summaries = openai_processor.generate_summaries(article.content)
            tags = openai_processor.generate_tags(article.content)
            article.summary_20 = summaries["20_words"]
            article.summary_50 = summaries["50_words"]
            article.summary_100 = summaries["100_words"]
            article.unlimited_summary = summaries["unlimited"]
            article.tags = ",".join(tags)
            session.commit()
            logger.info(f"Article {article.pocket_id} processed successfully.")
        except Exception as e:
            logger.error(f"Error processing article {article.pocket_id}: {e}")
