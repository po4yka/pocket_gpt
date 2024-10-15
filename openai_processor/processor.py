from functools import lru_cache
from typing import Dict, List, Optional

import openai
from loguru import logger

from config import OPENAI_API_KEY


class OpenAIProcessor:
    def __init__(self):
        openai.api_key = OPENAI_API_KEY
        self.model = "gpt-4o"

    def _call_openai_api(self, system_message: str, user_message: str) -> str:
        """Call OpenAI API with error handling."""
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise

    @lru_cache(maxsize=128)
    def _cached_api_call(self, system_message: str, user_message: str) -> str:
        """Cached version of the API call."""
        return self._call_openai_api(system_message, user_message)

    def _generate_summary(self, content: str, word_limit: Optional[int] = None) -> str:
        """Generate a summary with a specified word limit or unlimited length."""
        system_message = "You are a helpful assistant that summarizes articles " "concisely and accurately."

        if word_limit:
            user_message = (
                f"Summarize the following content in exactly {word_limit} words. "
                f"Prioritize key points and maintain clarity:\n\n{content}\n\n"
                f"Summary ({word_limit} words):"
            )
        else:
            user_message = (
                "Provide a comprehensive summary of the following content "
                f"without any word limit. Capture all key points:\n\n{content}\n\n"
                "Unlimited Summary:"
            )

        logger.info(f"Generating {'unlimited' if not word_limit else f'{word_limit}-word'} " "summary...")
        return self._cached_api_call(system_message, user_message)

    def generate_summaries(self, content: str) -> Dict[str, str]:
        """Generate summaries in 20, 50, 100 words, and unlimited length."""
        word_limits = [20, 50, 100, None]
        return {
            f"{'unlimited' if limit is None else f'{limit}_words'}": self._generate_summary(content, limit)
            for limit in word_limits
        }

    def generate_tags(self, content: str) -> List[str]:
        """Generate relevant tags for the content."""
        system_message = "You are a helpful assistant that generates relevant and concise " "tags for articles."
        user_message = (
            "Generate a comma-separated list of relevant tags based on the key "
            f"topics and themes in the following content:\n\n{content}\n\nTags:"
        )

        logger.info("Generating tags...")
        tags_text = self._cached_api_call(system_message, user_message)
        return [tag.strip() for tag in tags_text.split(",") if tag.strip()]
