import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Pocket API credentials
POCKET_CONSUMER_KEY = os.getenv("POCKET_CONSUMER_KEY")
POCKET_ACCESS_TOKEN = os.getenv("POCKET_ACCESS_TOKEN")

# OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Firecrawl API key
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# Database configuration
DATABASE_URL = "sqlite:///data/articles.db"

# Logging configuration
LOG_FILE_PATH = "logs/pocket_gpt.log"
LOG_LEVEL = "INFO"
