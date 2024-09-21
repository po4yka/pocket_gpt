import openai

from pocket_gpt.config import OPENAI_API_KEY


class OpenAIProcessor:
    def __init__(self):
        openai.api_key = OPENAI_API_KEY

    def generate_summary(self, content):
        prompt = f"Summarize the following article:\n\n{content}"
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes articles.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
        )
        summary = response["choices"][0]["message"]["content"]
        return summary.strip()

    def generate_tags(self, content):
        prompt = f"Generate a list of relevant tags for the following article content:\n\n{content}"
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that generates tags for articles.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=60,
        )
        tags_text = response["choices"][0]["message"]["content"]
        tags = [tag.strip() for tag in tags_text.replace("\n", ",").split(",") if tag.strip()]
        return tags
