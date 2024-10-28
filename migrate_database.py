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
        # SQLite doesn't have a native JSON type, but we'll use TEXT
        # SQLAlchemy will handle JSON serialization/deserialization
        return "TEXT"
    elif isinstance(column.type, DateTime):
        return "DATETIME"
    elif isinstance(column.type, Integer):
        return "INTEGER"
    elif isinstance(column.type, String):
        return "TEXT"
    return str(column.type.compile())


def convert_existing_json_data(engine: Engine) -> None:
    """Convert existing JSON data to ensure proper format."""
    try:
        with engine.connect() as conn:
            # Check if firecrawl_metadata column exists
            columns = conn.execute(text("PRAGMA table_info(articles)")).fetchall()
            if any(col[1] == "firecrawl_metadata" for col in columns):
                # Get all rows with non-null firecrawl_metadata
                rows = conn.execute(
                    text("SELECT id, firecrawl_metadata FROM articles WHERE firecrawl_metadata IS NOT NULL")
                ).fetchall()

                for row in rows:
                    try:
                        # If the data is already in proper JSON format, this will work
                        import json

                        metadata_str = row[1]
                        if isinstance(metadata_str, str):
                            # Try to parse and re-stringify to ensure proper format
                            json_data = json.loads(metadata_str)
                            formatted_json = json.dumps(json_data)

                            # Update the row with properly formatted JSON
                            conn.execute(
                                text("UPDATE articles SET firecrawl_metadata = :metadata WHERE id = :id"),
                                {"metadata": formatted_json, "id": row[0]},
                            )
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to convert JSON data for article ID {row[0]}: {e}")
                        # Set to NULL if invalid
                        conn.execute(
                            text("UPDATE articles SET firecrawl_metadata = NULL WHERE id = :id"), {"id": row[0]}
                        )

                conn.commit()
                logger.info("Existing JSON data conversion completed")
    except Exception as e:
        logger.error(f"Error converting existing JSON data: {e}")


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

        # Convert existing JSON data to proper format
        convert_existing_json_data(engine)

        logger.info("Database migration completed successfully")

        # Create index for better performance
        with engine.connect() as conn:
            # Remove old index if exists (in case of schema changes)
            conn.execute(text("DROP INDEX IF EXISTS idx_firecrawl_metadata"))
            # Create new index
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
