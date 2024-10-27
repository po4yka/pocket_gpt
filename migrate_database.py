from loguru import logger
from sqlalchemy import JSON, DateTime, Integer, String, create_engine, text
from sqlalchemy.engine import Engine

from config import DATABASE_URL
from models import Article


def backup_database(engine: Engine) -> bool:
    """Backup the existing database before migration."""
    try:
        with engine.connect() as conn:
            # Read all data from the articles table
            conn.execute(text("SELECT * FROM articles")).fetchall()

            # Create a backup table
            conn.execute(text("CREATE TABLE IF NOT EXISTS articles_backup AS SELECT * FROM articles"))
            conn.commit()

        logger.info("Database backup created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to create database backup: {e}")
        return False


def get_column_type(column_name: str) -> str:
    """Get the SQLite column type for a given model column."""
    column = Article.__table__.columns[column_name]
    if isinstance(column.type, JSON):
        return "TEXT"  # SQLite doesn't have a native JSON type
    elif isinstance(column.type, DateTime):
        return "DATETIME"
    elif isinstance(column.type, Integer):
        return "INTEGER"
    elif isinstance(column.type, String):
        return "TEXT"
    return str(column.type.compile())


def migrate_database():
    """Migrate the database to match the current model schema."""
    engine = create_engine(DATABASE_URL)

    try:
        # Create backup first
        if not backup_database(engine):
            logger.error("Migration aborted due to backup failure")
            return False

        # Get existing columns
        with engine.connect() as conn:
            existing_columns = [col[1] for col in conn.execute(text("PRAGMA table_info(articles)")).fetchall()]

        # Add missing columns
        with engine.connect() as conn:
            new_columns = [
                "content_html",
                "firecrawl_metadata",
                "author",
                "published_date",
                "word_count",
                "estimated_reading_time",
            ]
            for column in new_columns:
                if column not in existing_columns:
                    col_type = get_column_type(column)
                    conn.execute(text(f"ALTER TABLE articles ADD COLUMN {column} {col_type}"))
                    logger.info(f"Added column: {column} ({col_type})")

            conn.commit()

        logger.info("Database migration completed successfully")

        # Create JSON index if needed (optional, for better performance)
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_firecrawl_metadata
                ON articles(firecrawl_metadata)
            """
                )
            )
            conn.commit()

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def verify_schema():
    """Verify that the database schema matches the model."""
    engine = create_engine(DATABASE_URL)

    # Reflect existing tables
    from sqlalchemy import MetaData

    metadata = MetaData()
    metadata.reflect(bind=engine)

    # Check if all model columns exist in the database
    if "articles" in metadata.tables:
        db_columns = set(metadata.tables["articles"].columns.keys())
        model_columns = {column.key for column in Article.__table__.columns}

        missing_columns = model_columns - db_columns
        if missing_columns:
            logger.error(f"Missing columns in database: {missing_columns}")
            return False

    logger.info("Database schema verification completed successfully")
    return True


if __name__ == "__main__":
    logger.info("Starting database migration...")

    if migrate_database():
        if verify_schema():
            logger.info("Migration and verification completed successfully")
        else:
            logger.error("Schema verification failed after migration")
    else:
        logger.error("Migration failed")
