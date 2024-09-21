import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL
from models import Base


def get_engine():
    # Ensure the data directory exists
    data_dir = os.path.dirname(DATABASE_URL.replace("sqlite:///", ""))
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    engine = create_engine(DATABASE_URL)
    return engine


def get_session():
    engine = get_engine()
    # Create all tables if they don't exist
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
