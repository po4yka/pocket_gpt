import openai
from loguru import logger

from config import OPENAI_API_KEY


class OpenAIProcessor:
    def __init__(self):
        openai.api_key = OPENAI_API_KEY

    def _generate_summary(self, content, word_limit=None):
        """Generate a summary with a specified word limit or unlimited length."""
        if word_limit:
            prompt = f"""
You are a helpful assistant. Below is the content of an article.
Your task is to summarize it in exactly {word_limit} words.
Be concise, maintain clarity, and prioritize key points.

Content:
{content}

Summary ({word_limit} words):
"""
        else:
            prompt = f"""
You are a helpful assistant. Below is the content of an article.
Your task is to summarize it without any word limit.
Provide a complete, coherent summary that captures all key points.

Content:
{content}

Unlimited Summary:
"""
        logger.info(f"Generating {'unlimited' if not word_limit else f'{word_limit}-word'} summary...")
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4-0613",  # Latest GPT-4 model
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes articles."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000 if word_limit is None else 500,
            )
            summary = response.choices[0].message.content.strip()
            logger.info(f"{'Unlimited' if not word_limit else f'{word_limit}-word'} summary generated successfully.")
            return summary
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            raise

    def generate_summaries(self, content):
        """Generate summaries in 20, 50, 100 words, and unlimited length."""
        summaries = {}
        word_limits = [20, 50, 100, None]  # None represents unlimited summary
        for limit in word_limits:
            summary_type = "unlimited" if limit is None else f"{limit}_words"
            summaries[summary_type] = self._generate_summary(content, limit)
        return summaries

    def generate_tags(self, content):
        """Generate relevant tags for the content."""
        prompt = f"""
Below is the content of an article. Generate a list of tags based on the key topics and themes present.

Content:
{content}

Tags:
"""
        logger.info("Generating tags...")
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4-0613",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates tags for articles."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=60,
            )
            tags_text = response.choices[0].message.content.strip()
            tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
            logger.info("Tags generated successfully.")
            return tags
        except Exception as e:
            logger.error(f"Error generating tags: {e}")
            raise
