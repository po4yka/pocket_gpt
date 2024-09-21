import os

from loguru import logger


def setup_logging():
    if not os.path.exists("logs"):
        os.makedirs("logs")
    logger.add("logs/pocket_gpt.log", rotation="10 MB", retention="10 days", level="INFO")
