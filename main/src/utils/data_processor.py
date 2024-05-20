from services.openai_service import generate_summary, generate_tags
from services.postlight_service import retrieve_article_content


def process_article(article):
    # Retrieve full article content from Postlight Parser API
    article_content = retrieve_article_content(article['resolved_url'])

    # Extract necessary fields
    title = article_content.get('title', article['resolved_title'])
    content = article_content.get('content', '')
    author = article_content.get('author', '')
    date_published = article_content.get('date_published', '')
    lead_image_url = article_content.get('lead_image_url', '')
    excerpt = article_content.get('excerpt', article.get('excerpt', ''))
    word_count = article_content.get(
        'word_count', article.get('word_count', 0))
    direction = article_content.get('direction', '')
    total_pages = article_content.get('total_pages', 1)
    rendered_pages = article_content.get('rendered_pages', 1)

    summary = generate_summary(content)
    tags = generate_tags(content)

    return {
        'title': title,
        'url': article['resolved_url'],
        'content': content,
        'author': author,
        'date_published': date_published,
        'lead_image_url': lead_image_url,
        'excerpt': excerpt,
        'word_count': word_count,
        'direction': direction,
        'total_pages': total_pages,
        'rendered_pages': rendered_pages,
        'summary': summary,
        'tags': tags
    }
