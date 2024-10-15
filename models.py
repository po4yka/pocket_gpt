from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pocket_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_20: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_50: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_100: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unlimited_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pocket_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_added: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    firecrawl_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, pocket_id='{self.pocket_id}', title='{self.title}')>"
