from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    id = mapped_column(Integer, primary_key=True)  # type: Mapped[int]
    pocket_id = mapped_column(String, unique=True, index=True)  # type: Mapped[str]
    title = mapped_column(String)  # type: Mapped[str]
    url = mapped_column(String)  # type: Mapped[str]
    content = mapped_column(Text)  # type: Mapped[str]
    summary = mapped_column(Text)  # type: Mapped[str]
    tags = mapped_column(Text)  # type: Mapped[str]
    pocket_data = mapped_column(Text)  # type: Mapped[str]  # Store all Pocket data as JSON
    date_added = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )  # type: Mapped[datetime.datetime]

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, pocket_id='{self.pocket_id}', title='{self.title}')>"
