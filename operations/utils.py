from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Article


def get_database_info(session: Session):
    total_articles = session.query(func.count(Article.id)).scalar()
    articles_with_content = session.query(func.count(Article.id)).filter(Article.content.isnot(None)).scalar()
    logger.info(f"Database Info: Total={total_articles}, With Content={articles_with_content}")
    return {
        "total": total_articles,
        "with_content": articles_with_content,
    }
