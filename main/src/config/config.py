from dotenv import load_dotenv
import os

load_dotenv()

POCKET_CONSUMER_KEY = os.getenv('POCKET_CONSUMER_KEY')
POCKET_ACCESS_TOKEN = os.getenv('POCKET_ACCESS_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
POSTLIGHT_API_KEY = os.getenv('POSTLIGHT_API_KEY')
