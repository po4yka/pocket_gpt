import os

from loguru import logger
from sqlalchemy import JSON, create_engine, inspect
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL
from models import Article, Base


def get_column_type(column):
    """Convert SQLAlchemy column type to SQLite type."""
    if isinstance(column.type, JSON):
        return "TEXT"  # SQLite stores JSON as TEXT
    return column.type.compile()


def ensure_schema_exists(engine):
    """Ensure all columns from the model exist in the database."""
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns("articles")}
    model_columns = {column.key for column in Article.__table__.columns}

    missing_columns = model_columns - existing_columns
    if missing_columns:
        logger.warning(f"Found missing columns: {missing_columns}")
        with engine.connect() as conn:
            for column in missing_columns:
                # Get the column from the model
                model_column = getattr(Article.__table__.c, column)
                col_type = get_column_type(model_column)
                sql = f"ALTER TABLE articles ADD COLUMN {column} {col_type}"
                try:
                    conn.execute(sql)
                    conn.commit()
                    logger.info(f"Added column: {column}")

                    # Create index for JSON columns if needed
                    if isinstance(model_column.type, JSON):
                        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{column} ON articles({column})")
                        conn.commit()
                        logger.info(f"Created index for JSON column: {column}")

                except Exception as e:
                    logger.error(f"Failed to add column {column}: {e}")


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

    # Ensure all columns exist
    ensure_schema_exists(engine)

    Session = sessionmaker(bind=engine)
    return Session()
