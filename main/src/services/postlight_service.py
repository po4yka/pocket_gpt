import requests

POSTLIGHT_API_URL = "https://mercury.postlight.com/parser?url="
POSTLIGHT_API_KEY = "your_postlight_api_key"


def retrieve_article_content(url):
    headers = {
        "x-api-key": POSTLIGHT_API_KEY
    }
    response = requests.get(POSTLIGHT_API_URL + url, headers=headers)
    return response.json()
