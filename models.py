from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime
import datetime

Base = declarative_base()


class Article(Base):
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True)
    pocket_id = Column(String, unique=True, index=True)
    title = Column(String)
    url = Column(String)
    content = Column(Text)
    summary = Column(Text)
    tags = Column(Text)
    pocket_data = Column(Text)  # Store all Pocket data as JSON
    date_added = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<Article(id={self.id}, pocket_id='{self.pocket_id}', title='{self.title}')>"
